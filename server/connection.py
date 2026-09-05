"""Обслуживание одного клиентского соединения.

Этап 2: байты из сокета собираются в кадры по разделителю, и эхо возвращается
покадрово. Разница с этапом 1 видна сразу: раньше два быстрых send() клиента
отражались одним слипшимся куском, теперь — двумя отдельными сообщениями.

Разбора JSON здесь пока нет, содержимое кадра сервер не интерпретирует.
Он появится на этапе 3.
"""
from __future__ import annotations

import logging
import socket

from common.framing import FrameReader, FrameTooLongError, encode_frame

from .config import ServerConfig

logger = logging.getLogger("server.connection")

Address = tuple[str, int]

# Ответ на нарушение фрейминга. На этапе 3 станет полноценным JSON с кодом
# ошибки, пока — простой текстовый маркер.
FRAME_TOO_LONG_NOTICE = b"FRAME_TOO_LONG"

# Пределы «вежливого» закрытия после ошибки протокола.
DRAIN_TIMEOUT = 1.0
DRAIN_LIMIT = 64 * 1024


def handle_connection(sock: socket.socket, addr: Address, config: ServerConfig) -> None:
    """Обслужить одного клиента до отключения.

    Вызывающая сторона отвечает за закрытие сокета — здесь только обмен.
    """
    peer = f"{addr[0]}:{addr[1]}"
    logger.info("Клиент подключился: %s", peer)

    # Молчащий клиент не должен занимать соединение бесконечно.
    sock.settimeout(config.idle_timeout)

    reader = FrameReader(config.max_frame_size)
    frames_total = 0

    try:
        while True:
            try:
                chunk = sock.recv(config.recv_size)
            except TimeoutError:
                logger.warning(
                    "Клиент %s молчал %.0f с, закрываю соединение", peer, config.idle_timeout
                )
                break

            # Ноль байт — единственный корректный признак того, что
            # противоположная сторона закрыла соединение. Не исключение,
            # не таймаут, а именно пустой результат чтения.
            if not chunk:
                logger.info("Клиент %s закрыл соединение", peer)
                break

            logger.debug("От %s прочитано %d байт", peer, len(chunk))

            try:
                frames = reader.feed(chunk)
            except FrameTooLongError as exc:
                # Продолжать нельзя: позиция в потоке потеряна, неизвестно,
                # где заканчивается текущее сообщение и начинается следующее.
                logger.warning(
                    "Клиент %s превысил предельный размер кадра (%d байт), закрываю соединение",
                    peer,
                    exc.limit,
                )
                _try_send(sock, encode_frame(FRAME_TOO_LONG_NOTICE), peer)
                _close_gracefully(sock, peer)
                break

            # Одно чтение из сокета не равно одному сообщению ни в какую
            # сторону: кадров может прийти несколько, а может не прийти ни одного.
            for frame in frames:
                frames_total += 1
                logger.debug("Кадр от %s (%d байт): %r", peer, len(frame), frame)
                # sendall, а не send: send отправляет столько, сколько получилось,
                # и остаток пришлось бы досылать вручную.
                sock.sendall(encode_frame(frame))

            if not frames:
                logger.debug("Кадр от %s ещё не завершён, в буфере %d байт", peer, reader.pending)

    except ConnectionError as exc:
        # Клиент закрыл окно или оборвал связь на полуслове — штатная ситуация,
        # а не сбой сервера. Ловим родителя всего семейства: разные системы
        # сообщают об обрыве по-разному (ConnectionResetError на Linux,
        # ConnectionAbortedError на Windows), и перечислять их поимённо —
        # верный способ пропустить один и залить лог ложными ошибками.
        logger.info("Соединение с %s разорвано клиентом (%s)", peer, type(exc).__name__)
    except OSError as exc:
        logger.error("Ошибка сокета при работе с %s: %s", peer, exc)
    finally:
        logger.info("Клиент отключился: %s (обработано кадров: %d)", peer, frames_total)


def _try_send(sock: socket.socket, data: bytes, peer: str) -> None:
    """Отправить, не поднимая шума, если клиент уже ушёл.

    Сообщение об ошибке — вежливость, а не обязанность. Если отправить его
    не удалось, настоящая причина закрытия соединения не должна потеряться
    за исключением из этой попытки.
    """
    try:
        sock.sendall(data)
    except OSError as exc:
        logger.debug("Не удалось отправить уведомление клиенту %s: %s", peer, exc)


def _close_gracefully(sock: socket.socket, peer: str) -> None:
    """Закрыть соединение так, чтобы клиент успел прочитать уведомление.

    Если просто закрыть сокет, когда во входящем буфере остались непрочитанные
    данные, система отправляет RST — аварийный сброс. При нём уже отправленное
    уведомление может быть отброшено, и клиент вместо внятного «кадр слишком
    длинный» увидит «соединение разорвано». Проверено: именно так и вело себя
    закрытие после превышения лимита.

    Правильная последовательность: сообщить, что мы больше ничего не пришлём,
    затем вычитать и выбросить остаток, пока клиент не закроет свою сторону.

    Пределы по объёму и времени обязательны: без них клиент, продолжающий
    слать данные, удержит поток навсегда — то есть защита от переполнения
    буфера обернулась бы новым способом занять сервер.
    """
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        # Клиент уже ушёл — дочитывать нечего и незачем.
        return

    sock.settimeout(DRAIN_TIMEOUT)
    discarded = 0
    try:
        while discarded < DRAIN_LIMIT:
            chunk = sock.recv(4096)
            if not chunk:
                break
            discarded += len(chunk)
    except OSError:
        pass

    if discarded:
        logger.debug("От %s отброшено %d байт после ошибки протокола", peer, discarded)
