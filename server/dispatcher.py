"""Сопоставление имени команды с обработчиком.

Словарь вместо цепочки if-elif: добавление команды не требует правок в
обработке запросов, а список поддерживаемых команд доступен для самопроверки.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .protocol import ErrorCode, ProtocolError, Request
from .session import Session

Handler = Callable[[Request, Session], Any]


class Dispatcher:
    """Реестр команд."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, name: str, handler: Handler) -> None:
        """Добавить команду."""
        if name in self._handlers:
            # Тихая перезапись привела бы к тому, что часть команд молча
            # перестаёт работать. Лучше упасть при запуске.
            raise ValueError(f"Команда {name!r} уже зарегистрирована")
        self._handlers[name] = handler

    @property
    def commands(self) -> list[str]:
        """Имена всех зарегистрированных команд."""
        return sorted(self._handlers)

    def dispatch(self, request: Request, session: Session) -> Any:
        """Выполнить команду и вернуть её результат."""
        handler = self._handlers.get(request.cmd)
        if handler is None:
            raise ProtocolError(
                ErrorCode.UNKNOWN_COMMAND,
                f"Неизвестная команда {request.cmd!r}. Доступны: {', '.join(self.commands)}",
            )
        return handler(request, session)
