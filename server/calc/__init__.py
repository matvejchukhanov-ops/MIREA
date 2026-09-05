"""Вычислительное ядро калькулятора.

Пакет ничего не знает о сокетах, кадрах и JSON: снаружи это функция
«строка → число». Благодаря этому он тестируется без запуска сервера —
и отладка парсера не смешивается с отладкой сети.

Здесь не используется eval(). Строка приходит из сети, а eval() выполняет
любой код Python, а не только арифметику: клиент, приславший вместо «2+2»
подходящее выражение, получил бы возможность выполнять команды на сервере.
Данные из сети не являются кодом и не должны им становиться.

    >>> calculate("2 + 3 * 4")
    14
"""
from __future__ import annotations

from .errors import (
    CalcError,
    DepthExceededError,
    DivisionByZeroError,
    ExpressionSyntaxError,
    ExpressionTooLongError,
    NumberTooLargeError,
    UnknownCharError,
)
from .evaluator import evaluate
from .lexer import tokenize
from .parser import parse

# Предел длины выражения — из спецификации протокола.
MAX_EXPRESSION_LENGTH = 1000

__all__ = [
    "CalcError",
    "DepthExceededError",
    "DivisionByZeroError",
    "ExpressionSyntaxError",
    "ExpressionTooLongError",
    "MAX_EXPRESSION_LENGTH",
    "NumberTooLargeError",
    "UnknownCharError",
    "calculate",
    "evaluate",
    "parse",
    "tokenize",
]


def calculate(expression: str) -> int | float:
    """Вычислить арифметическое выражение.

    Все ошибки — потомки CalcError и несут позицию символа в строке.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionTooLongError(
            f"Выражение длиннее {MAX_EXPRESSION_LENGTH} символов", position=MAX_EXPRESSION_LENGTH
        )
    return evaluate(parse(tokenize(expression)))
