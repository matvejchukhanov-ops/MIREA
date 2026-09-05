"""Точка входа клиента.

Этап 2: отправляет введённую строку одним кадром и печатает кадр, пришедший
в ответ. Нужен потому, что telnet-клиент в Windows по умолчанию отключён,
а проверить сервер чем-то надо.

Запуск:
    python -m client.main
    python -m client.main --host 127.0.0.1 --port 9000

Выход — команда `quit` или Ctrl+C.
"""
from __future__ import annotations

import argparse
import sys

from common.framing import FrameTooLongError

from .connection import ServerClosedConnection, ServerConnection

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

EXIT_COMMANDS = {"quit", "exit", "выход"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="client",
        description="Клиент калькулятора выражений (этап 2: эхо покадрово)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Адрес сервера")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт сервера")
    return parser


def run_session(connection: ServerConnection) -> None:
    """Цикл «ввод — отправка — ответ»."""
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

        try:
            connection.send(line.encode("utf-8"))
            reply = connection.receive()
        except FrameTooLongError as exc:
            print(f"Сообщение слишком длинное: {exc}")
            continue
        except TimeoutError:
            print("Сервер не ответил за отведённое время")
            return
        except ServerClosedConnection:
            print("Сервер закрыл соединение")
            return
        except OSError as exc:
            print(f"Ошибка соединения: {exc}")
            return

        print(reply.decode("utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        with ServerConnection.connect(args.host, args.port) as connection:
            run_session(connection)
    except (ConnectionRefusedError, TimeoutError):
        print(f"Сервер {args.host}:{args.port} недоступен. Запущен ли он?", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Ошибка соединения: {exc}", file=sys.stderr)
        return 1

    print("Отключено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
