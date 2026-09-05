"""Слушающий сокет и цикл приёма подключений.

Клиенты пока обслуживаются по очереди, в одном потоке. Это сделано намеренно —
так видно, ради чего на этапе 7 появятся потоки: пока сервер разговаривает
с одним клиентом, он не возвращается к accept(), и второй клиент ждёт
в очереди.
"""
from __future__ import annotations

import logging
import socket

from .config import ServerConfig
from .connection import handle_connection
from .handlers import build_dispatcher

logger = logging.getLogger("server.tcp")

# Как часто accept() «просыпается», чтобы Python успел обработать сигналы.
# Без этого блокирующий accept() на Windows не прерывается по Ctrl+C, пока
# не подключится очередной клиент.
ACCEPT_POLL_INTERVAL = 0.5


class TCPServer:
    """TCP-сервер: принимает подключения и передаёт их обработчику."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._socket: socket.socket | None = None
        self._running = False
        # Реестр команд собирается один раз при запуске: после сборки он
        # только читается, поэтому его безопасно делить между соединениями.
        self._dispatcher = build_dispatcher()

    def serve_forever(self) -> None:
        """Принимать подключения, пока не остановят."""
        self._socket = self._create_listening_socket()
        self._running = True

        host, port = self._config.address
        logger.info("Сервер слушает %s:%d", host, port)
        logger.info("Доступные команды: %s", ", ".join(self._dispatcher.commands))
        logger.info("Остановка — Ctrl+C")

        try:
            while self._running:
                try:
                    client_socket, addr = self._socket.accept()
                except TimeoutError:
                    # Ожидаемое срабатывание таймаута опроса, не ошибка.
                    continue
                except OSError:
                    if not self._running:
                        break
                    raise

                # Контекстный менеджер закрывает сокет клиента в любом случае,
                # включая исключение внутри обработчика.
                with client_socket:
                    handle_connection(client_socket, addr, self._config, self._dispatcher)

        except KeyboardInterrupt:
            logger.info("Получен сигнал прерывания")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Прекратить приём подключений и освободить порт."""
        self._running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None
            logger.info("Сервер остановлен")

    def _create_listening_socket(self) -> socket.socket:
        """Создать, настроить и перевести в режим прослушивания."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _configure_address_reuse(sock)
            sock.settimeout(ACCEPT_POLL_INTERVAL)
            sock.bind(self._config.address)
            sock.listen(self._config.backlog)
        except OSError:
            sock.close()
            raise
        return sock


def _configure_address_reuse(sock: socket.socket) -> None:
    """Разрешить повторную привязку к порту после перезапуска.

    После остановки сервера соединения остаются в состоянии TIME_WAIT, и
    повторный запуск может упасть с «адрес уже используется». На отладке
    перезапуск происходит десятки раз в час, поэтому вопрос не теоретический.

    Правильный флаг зависит от системы:

    * Windows — SO_EXCLUSIVEADDRUSE. Здесь SO_REUSEADDR означает совсем другое:
      он позволяет чужому процессу привязаться к уже занятому порту и
      перехватывать подключения. Использовать его на Windows опасно.
    * POSIX — SO_REUSEADDR. Разрешает занять порт, висящий в TIME_WAIT, но
      не отнимает порт у работающего процесса.
    """
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
