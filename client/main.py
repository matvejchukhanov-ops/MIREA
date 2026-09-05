"""Точка входа клиента.

Этап 3: клиент формирует запросы по протоколу и разбирает ответы.

Что можно ввести:
    ping            проверка связи
    history         последние вычисления (появится на этапе 6)
    history 5       то же, с ограничением количества
    2 + 2           выражение (команда calc, появится на этапе 4)
    {"cmd":"..."}   сырой JSON — чтобы проверить поведение протокола вручную
    quit            выход

Запуск:
    python -m client.main
    python -m client.main --host 127.0.0.1 --port 9000
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from common.framing import FrameTooLongError

from .connection import ServerClosedConnection, ServerConnection

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

EXIT_COMMANDS = {"quit", "exit", "выход"}
NO_ARG_COMMANDS = {"ping"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="client",
        description="Клиент калькулятора выражений",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Адрес сервера")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Порт сервера")
    return parser


def build_request(line: str) -> dict[str, Any]:
    """Превратить введённую строку в запрос по протоколу."""
    text = line.strip()
    lowered = text.lower()

    # Сырой JSON пропускаем как есть: так можно вручную проверить, как сервер
    # реагирует на нарушения протокола, не переписывая клиент.
    if text.startswith("{"):
        return json.loads(text)

    if lowered in EXIT_COMMANDS:
        return {"cmd": "quit"}

    if lowered in NO_ARG_COMMANDS:
        return {"cmd": lowered}

    if lowered == "history" or lowered.startswith("history "):
        _, _, tail = text.partition(" ")
        request: dict[str, Any] = {"cmd": "history"}
        if tail.strip():
            request["limit"] = int(tail.strip())
        return request

    # Всё остальное считаем выражением.
    return {"cmd": "calc", "expr": text}


def format_response(data: Any, source_line: str) -> str:
    """Подготовить ответ сервера к выводу человеку."""
    if not isinstance(data, dict):
        return f"Неожиданный ответ сервера: {data!r}"

    status = data.get("status")

    if status == "ok":
        result = data.get("result")
        if isinstance(result, list):
            if not result:
                return "(пусто)"
            return "\n".join(f"  {item}" for item in result)
        return str(result)

    if status == "error":
        message = f"Ошибка [{data.get('code')}]: {data.get('message')}"
        position = data.get("position")
        if isinstance(position, int) and 0 <= position <= len(source_line):
            # Указатель на место ошибки: строка пробелов и стрелка.
            message += f"\n  {source_line}\n  {' ' * position}^"
        return message

    # Поле status обязано быть всегда — его отсутствие означает,
    # что мы разговариваем не с тем сервером.
    return f"Ответ без поля status: {data!r}"


def run_session(connection: ServerConnection) -> None:
    """Цикл «ввод — запрос — ответ»."""
    print("Подключено. `ping` — проверка связи, `quit` — выход.\n")

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not line.strip():
            continue

        try:
            request = build_request(line)
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Не удалось составить запрос: {exc}")
            continue

        try:
            connection.send(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            reply = connection.receive()
        except FrameTooLongError as exc:
            print(f"Ответ сервера не укладывается в допустимый размер: {exc}")
            return
        except TimeoutError:
            print("Сервер не ответил за отведённое время")
            return
        except ServerClosedConnection:
            print("Сервер закрыл соединение")
            return
        except OSError as exc:
            print(f"Ошибка соединения: {exc}")
            return

        try:
            data = json.loads(reply.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"Ответ сервера не разбирается как JSON: {reply!r}")
            continue

        print(format_response(data, line.strip()))

        if request.get("cmd") == "quit":
            return


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
