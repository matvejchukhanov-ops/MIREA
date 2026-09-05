"""Точка входа клиента.

Этап 1: отправляет введённую строку и печатает то, что вернул сервер.
Нужен потому, что telnet-клиент в Windows по умолчанию отключён, а проверить
эхо-сервер чем-то надо.

Запуск:
    python -m client.main
    python -m client.main --host 127.0.0.1 --port 9000

Выход — команда `quit` или Ctrl+C.
"""
from __future__ import annotations

import argparse
import socket
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
RECV_SIZE = 4096
CONNECT_TIMEOUT = 5.0
REPLY_TIMEOUT = 10.0

EXIT_COMMANDS = {"quit", "exit", "выход"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="client",
        description="Клиент калькулятора выражений (этап 1: эхо)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Адрес сервера")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт сервера")
    return parser


def run_session(sock: socket.socket) -> None:
    """Цикл «ввод — отправка — ответ»."""
    sock.settimeout(REPLY_TIMEOUT)
    print("Подключено. Введите текст, `quit` — выход.\n")

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not line:
            continue
        if line.strip().lower() in EXIT_COMMANDS:
            return

        sock.sendall(line.encode("utf-8"))

        try:
            reply = sock.recv(RECV_SIZE)
        except TimeoutError:
            print("Сервер не ответил за отведённое время")
            return

        # Ноль байт — сервер закрыл соединение.
        if not reply:
            print("Сервер закрыл соединение")
            return

        print(reply.decode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        with socket.create_connection((args.host, args.port), timeout=CONNECT_TIMEOUT) as sock:
            run_session(sock)
    except (ConnectionRefusedError, TimeoutError):
        print(
            f"Сервер {args.host}:{args.port} недоступен. Запущен ли он?",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Ошибка соединения: {exc}", file=sys.stderr)
        return 1

    print("Отключено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
