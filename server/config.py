"""Конфигурация сервера.

Приоритет источников: аргументы командной строки, затем переменные окружения,
затем умолчания из этого модуля. Порядок именно такой — явное указание при
запуске перекрывает окружение, окружение перекрывает умолчания.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from common.framing import MAX_FRAME_SIZE as DEFAULT_MAX_FRAME_SIZE

# --- Умолчания ---

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

# Размер очереди подключений: сколько клиентов ОС подержит в ожидании, пока
# сервер занят предыдущим вызовом accept().
DEFAULT_BACKLOG = 16

# Сколько байт запрашиваем у сокета за одно чтение. Это НЕ размер сообщения:
# recv() вправе вернуть меньше запрошенного и почти всегда так и делает.
DEFAULT_RECV_SIZE = 4096

# Сколько секунд ждать данных от молчащего клиента, прежде чем закрыть
# соединение. Без таймаута забытое соединение занимает ресурсы бесконечно.
DEFAULT_IDLE_TIMEOUT = 300.0

# Сколько клиентов обслуживать одновременно. Каждый занимает поток, а поток
# стоит памяти под стек: без предела клиент, открывающий соединения пачками,
# исчерпает ресурсы машины.
DEFAULT_MAX_CONNECTIONS = 64

DEFAULT_LOG_LEVEL = "INFO"

_MIN_PORT = 1
_MAX_PORT = 65535
_PRIVILEGED_PORT_MAX = 1023


class ConfigError(ValueError):
    """Некорректное значение конфигурации."""


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Параметры запуска сервера."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    backlog: int = DEFAULT_BACKLOG
    recv_size: int = DEFAULT_RECV_SIZE
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    max_connections: int = DEFAULT_MAX_CONNECTIONS
    log_level: str = DEFAULT_LOG_LEVEL

    def __post_init__(self) -> None:
        if not self.host:
            raise ConfigError("Адрес не может быть пустым")
        if not _MIN_PORT <= self.port <= _MAX_PORT:
            raise ConfigError(
                f"Порт должен быть в диапазоне {_MIN_PORT}-{_MAX_PORT}, получено {self.port}"
            )
        if self.backlog < 1:
            raise ConfigError("Размер очереди подключений должен быть не меньше 1")
        if self.recv_size < 1:
            raise ConfigError("Размер буфера чтения должен быть не меньше 1")
        if self.max_frame_size < 2:
            raise ConfigError("Предельный размер кадра должен вмещать байт и разделитель")
        if self.idle_timeout <= 0:
            raise ConfigError("Таймаут бездействия должен быть положительным")
        if self.max_connections < 1:
            raise ConfigError("Число одновременных подключений должно быть не меньше 1")

    @property
    def address(self) -> tuple[str, int]:
        """Адрес в виде, который принимают методы сокета."""
        return self.host, self.port

    @property
    def needs_privileges(self) -> bool:
        """Порты до 1024 требуют прав администратора."""
        return self.port <= _PRIVILEGED_PORT_MAX

    @classmethod
    def from_env(cls) -> ServerConfig:
        """Собрать конфигурацию из переменных окружения."""
        return cls(
            host=os.environ.get("CALC_HOST", DEFAULT_HOST),
            port=_env_int("CALC_PORT", DEFAULT_PORT),
            backlog=_env_int("CALC_BACKLOG", DEFAULT_BACKLOG),
            recv_size=_env_int("CALC_RECV_SIZE", DEFAULT_RECV_SIZE),
            max_frame_size=_env_int("CALC_MAX_FRAME_SIZE", DEFAULT_MAX_FRAME_SIZE),
            idle_timeout=_env_float("CALC_IDLE_TIMEOUT", DEFAULT_IDLE_TIMEOUT),
            max_connections=_env_int("CALC_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS),
            log_level=os.environ.get("CALC_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть целым числом, получено {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть числом, получено {raw!r}") from exc
