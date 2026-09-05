"""Обслуживание одного клиентского соединения.

Этап 1: сервер возвращает клиенту ровно те байты, которые получил.

Границы сообщений здесь намеренно НЕ восстанавливаются. Эхо-сервер отражает
данные так, как они пришли из сокета, — и именно поэтому на нём хорошо видно,
что TCP не сохраняет границы: два быстрых send() на стороне клиента приходят
одним куском. Фрейминг по разделителю появится на этапе 2.
"""
from __future__ import annotations

import logging
import socket

from .config import ServerConfig

logger = logging.getLogger("server.connection")

Address = tuple[str, int]


def handle_connection(sock: socket.socket, addr: Address, config: ServerConfig) -> None:
    """Обслужить одного клиента до отключения.

    Вызывающая сторона отвечает за закрытие сокета — здесь только обмен.
    """
    peer = f"{addr[0]}:{addr[1]}"
    logger.info("Клиент подключился: %s", peer)

    # Молчащий клиент не должен занимать соединение бесконечно.
    sock.settimeout(config.idle_timeout)

    received_total = 0
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

            received_total += len(chunk)
            logger.debug("От %s получено %d байт: %r", peer, len(chunk), chunk)

            # sendall, а не send: send отправляет столько, сколько получилось,
            # и возвращает это число. Остаток пришлось бы досылать вручную.
            sock.sendall(chunk)

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
        logger.info("Клиент отключился: %s (получено %d байт)", peer, received_total)
