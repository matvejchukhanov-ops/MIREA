"""Точка входа сервера.

Запуск:
    python -m server.main
    python -m server.main --host 0.0.0.0 --port 9000 --log-level DEBUG
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from .config import ConfigError, ServerConfig
from .logging_setup import setup_logging
from .tcp_server import TCPServer

logger = logging.getLogger("server.main")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="server",
        description="Сервер калькулятора выражений (этап 1: эхо)",
    )
    parser.add_argument("--host", help="Адрес для прослушивания")
    parser.add_argument("--port", type=int, help="Порт для прослушивания")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень подробности логов",
    )
    parser.add_argument("--log-file", type=Path, help="Дополнительно писать логи в файл")
    return parser


def build_config(args: argparse.Namespace) -> ServerConfig:
    """Наложить аргументы командной строки поверх конфигурации из окружения."""
    config = ServerConfig.from_env()

    overrides = {
        name: value
        for name, value in (
            ("host", args.host),
            ("port", args.port),
            ("log_level", args.log_level),
        )
        if value is not None
    }
    return replace(config, **overrides) if overrides else config


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = build_config(args)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    setup_logging(config.log_level, args.log_file)

    if config.needs_privileges:
        logger.warning("Порт %d требует прав администратора", config.port)

    try:
        TCPServer(config).serve_forever()
    except OSError as exc:
        logger.error("Не удалось запустить сервер на %s:%d — %s", config.host, config.port, exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
