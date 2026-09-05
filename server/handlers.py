"""Обработчики команд.

Каждый принимает разобранный запрос и состояние соединения, возвращает то,
что попадёт в поле result ответа. О JSON, кадрах и сокетах обработчики
не знают ничего — этим занимаются слои выше.

Об ошибке сообщается исключением ProtocolError с кодом: превращать его
в ответ будет вызывающая сторона.
"""
from __future__ import annotations

from typing import Any

from .calc import (
    CalcError,
    DepthExceededError,
    DivisionByZeroError,
    ExpressionSyntaxError,
    ExpressionTooLongError,
    NumberTooLargeError,
    UnknownCharError,
    calculate,
)
from .dispatcher import Dispatcher
from .protocol import ErrorCode, ProtocolError, Request
from .session import HISTORY_CAPACITY, Session

DEFAULT_HISTORY_LIMIT = 10

# Сопоставление ошибок вычислительного ядра с кодами протокола.
#
# Таблица живёт здесь, а не в calc/, чтобы ядро оставалось независимым от
# протокола: «строка → число» должно работать и без сервера.
ERROR_CODES: dict[type[CalcError], ErrorCode] = {
    ExpressionTooLongError: ErrorCode.EXPR_TOO_LONG,
    UnknownCharError: ErrorCode.UNKNOWN_CHAR,
    ExpressionSyntaxError: ErrorCode.SYNTAX_ERROR,
    DepthExceededError: ErrorCode.DEPTH_EXCEEDED,
    DivisionByZeroError: ErrorCode.DIV_BY_ZERO,
    NumberTooLargeError: ErrorCode.NUMBER_TOO_LARGE,
}


def handle_ping(request: Request, session: Session) -> str:
    """Проверка живости соединения."""
    return "pong"


def handle_quit(request: Request, session: Session) -> str:
    """Завершение сеанса по инициативе клиента."""
    # Соединение закрывается не здесь: сначала нужно отправить ответ.
    session.should_close = True
    return "bye"


def handle_calc(request: Request, session: Session) -> int | float:
    """Вычислить выражение."""
    expression = request.require_str("expr")

    try:
        result = calculate(expression)
    except CalcError as exc:
        raise ProtocolError(
            _code_for(exc), exc.message, position=exc.position
        ) from exc

    session.remember(expression, result)
    return result


def handle_history(request: Request, session: Session) -> list[dict[str, Any]]:
    """Последние успешные вычисления в этом соединении."""
    limit = request.optional_int(
        "limit", DEFAULT_HISTORY_LIMIT, minimum=1, maximum=HISTORY_CAPACITY
    )
    return session.recent(limit)


def build_dispatcher() -> Dispatcher:
    """Собрать реестр команд.

    Вызывается один раз при запуске сервера. Реестр после сборки только
    читается, поэтому его безопасно делить между потоками.
    """
    dispatcher = Dispatcher()
    dispatcher.register("ping", handle_ping)
    dispatcher.register("calc", handle_calc)
    dispatcher.register("history", handle_history)
    dispatcher.register("quit", handle_quit)
    return dispatcher


def _code_for(error: CalcError) -> ErrorCode:
    """Подобрать код протокола для ошибки вычисления."""
    for error_type, code in ERROR_CODES.items():
        if isinstance(error, error_type):
            return code
    # Новый тип ошибки, не внесённый в таблицу. Отдать наружу нейтральный
    # код безопаснее, чем упасть: клиент получит ответ, а не разрыв.
    return ErrorCode.INTERNAL_ERROR
