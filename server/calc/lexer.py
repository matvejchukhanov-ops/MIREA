"""Лексер: строка в список токенов.

Первый из двух этапов разбора. Лексер отвечает на вопрос «какие символы
вообще допустимы», парсер — на вопрос «в каком порядке они могут стоять».
Смешав их, получаешь код, который невозможно ни читать, ни тестировать
по отдельности.

    "2 + 3*4"  ->  [ЧИСЛО 2] [ПЛЮС] [ЧИСЛО 3] [ЗВЁЗДОЧКА] [ЧИСЛО 4] [КОНЕЦ]
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from .errors import ExpressionSyntaxError, NumberTooLargeError, UnknownCharError

# Явный набор цифр, а не str.isdigit(). Последний считает цифрами и арабские
# «٣», и индийские «३», которые int() потом принимает, а float() — нет.
# Калькулятору такая экзотика не нужна, а расхождение поведения — источник
# трудноуловимых ошибок.
DIGITS = "0123456789"

# Предел длины записи одного числа. Без него строка из тысячи девяток
# превращается в целое, арифметика с которым занимает заметное время.
MAX_NUMBER_LITERAL = 100


class TokenType(StrEnum):
    NUMBER = "NUMBER"
    PLUS = "PLUS"
    MINUS = "MINUS"
    STAR = "STAR"
    SLASH = "SLASH"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    EOF = "EOF"


SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
}


@dataclass(frozen=True, slots=True)
class Token:
    """Единица разбора.

    Позиция хранится у каждого токена, чтобы сообщение об ошибке могло
    указать на конкретное место в исходной строке.
    """

    type: TokenType
    position: int
    value: int | float | None = None


def tokenize(text: str) -> list[Token]:
    """Разобрать строку на токены.

    Бросает UnknownCharError на недопустимом символе и NumberTooLargeError
    на слишком длинной записи числа.
    """
    tokens: list[Token] = []
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char.isspace():
            # Пробелы разделяют токены, но токенами не являются:
            # "2+2" и "  2  +  2  " дают одинаковый список.
            index += 1
            continue

        if char in DIGITS:
            token, index = _read_number(text, index)
            tokens.append(token)
            continue

        token_type = SINGLE_CHAR_TOKENS.get(char)
        if token_type is None:
            raise UnknownCharError(f"Недопустимый символ {char!r}", position=index)

        tokens.append(Token(token_type, index))
        index += 1

    # Явный признак конца избавляет парсер от проверки выхода за границу
    # списка в каждой функции разбора.
    tokens.append(Token(TokenType.EOF, length))
    return tokens


def _read_number(text: str, start: int) -> tuple[Token, int]:
    """Прочитать число, начиная с позиции start."""
    index = start
    length = len(text)

    while index < length and text[index] in DIGITS:
        index += 1

    is_float = False
    if index < length and text[index] == ".":
        dot_position = index
        index += 1
        if index >= length or text[index] not in DIGITS:
            raise ExpressionSyntaxError("После точки ожидалась цифра", position=dot_position)
        while index < length and text[index] in DIGITS:
            index += 1
        is_float = True

    if index < length and text[index] == ".":
        raise ExpressionSyntaxError("В записи числа больше одной точки", position=index)

    literal = text[start:index]
    if len(literal) > MAX_NUMBER_LITERAL:
        raise NumberTooLargeError(
            f"Запись числа длиннее {MAX_NUMBER_LITERAL} символов", position=start
        )

    if is_float:
        value: int | float = float(literal)
        if math.isinf(value):
            raise NumberTooLargeError("Число вне допустимого диапазона", position=start)
    else:
        value = int(literal)

    return Token(TokenType.NUMBER, start, value), index
