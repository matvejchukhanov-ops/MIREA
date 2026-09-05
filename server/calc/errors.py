"""Ошибки вычисления выражений.

Модуль ничего не знает ни о сети, ни о протоколе: он говорит, ЧТО не так,
а не каким кодом об этом сообщить клиенту. Сопоставление с кодами протокола
живёт в server/handlers.py — так вычислительное ядро остаётся пригодным
к использованию вне сервера.
"""
from __future__ import annotations


class CalcError(Exception):
    """Базовая ошибка вычисления.

    Позиция — индекс символа в исходной строке, с нуля. Без неё сообщение
    «синтаксическая ошибка» не помогает вообще: непонятно, где именно.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.position = position


class ExpressionTooLongError(CalcError):
    """Выражение длиннее допустимого."""


class UnknownCharError(CalcError):
    """В выражении встретился недопустимый символ."""


class ExpressionSyntaxError(CalcError):
    """Токены не складываются в грамматику.

    Названа не SyntaxError, чтобы не перекрывать встроенное исключение
    Python — иначе ошибка калькулятора смешалась бы с ошибкой самого кода.
    """


class DepthExceededError(CalcError):
    """Слишком глубокая вложенность.

    Защита от переполнения стека: парсер рекурсивного спуска уходит на
    уровень глубже на каждой открывающей скобке.
    """


class DivisionByZeroError(CalcError):
    """Деление на ноль."""


class NumberTooLargeError(CalcError):
    """Число или результат выходят за допустимый диапазон."""
