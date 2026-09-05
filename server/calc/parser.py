"""Парсер: токены в дерево разбора методом рекурсивного спуска.

Грамматика:

    выражение  :=  слагаемое  ( ( "+" | "-" )  слагаемое )*
    слагаемое  :=  множитель ( ( "*" | "/" )  множитель )*
    множитель  :=  ЧИСЛО
                |  "(" выражение ")"
                |  ( "-" | "+" ) множитель

Каждой строчке грамматики соответствует одна функция — в этом вся
привлекательность метода: грамматика читается как код, код читается
как грамматика.

Приоритет операций нигде не задан явно: ни таблицей, ни числами. Он
возникает из структуры. «Выражение» состоит из «слагаемых», а «слагаемое» —
из «множителей», поэтому умножение оказывается глубже в дереве, а дерево
вычисляется снизу вверх:

    2 + 3 * 4          (+)
                      /   \\
                    (2)   (*)
                         /   \\
                       (3)   (4)

Результат 14, а не 20. Чтобы добавить возведение в степень, достаточно
вставить ещё один уровень между «слагаемым» и «множителем».
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import DepthExceededError, ExpressionSyntaxError
from .lexer import Token, TokenType

# Предел вложенности. Каждая открывающая скобка уводит парсер на уровень
# рекурсии глубже, и строка из тысячи скобок переполнит стек — падение
# выглядело бы необъяснимо, потому что причина не в логике, а в среде
# выполнения. Осмысленные выражения такой вложенности не имеют.
MAX_DEPTH = 50


@dataclass(frozen=True, slots=True)
class Number:
    value: int | float
    position: int


@dataclass(frozen=True, slots=True)
class UnaryOp:
    operator: str
    operand: "Node"
    position: int


@dataclass(frozen=True, slots=True)
class BinaryOp:
    operator: str
    left: "Node"
    right: "Node"
    position: int


Node = Number | UnaryOp | BinaryOp

OPERATOR_BY_TOKEN: dict[TokenType, str] = {
    TokenType.PLUS: "+",
    TokenType.MINUS: "-",
    TokenType.STAR: "*",
    TokenType.SLASH: "/",
}

ADDITIVE = (TokenType.PLUS, TokenType.MINUS)
MULTIPLICATIVE = (TokenType.STAR, TokenType.SLASH)


def parse(tokens: list[Token], max_depth: int = MAX_DEPTH) -> Node:
    """Построить дерево разбора по списку токенов."""
    return Parser(tokens, max_depth).parse()


class Parser:
    """Рекурсивный спуск по грамматике.

    Идёт по списку токенов слева направо и никогда не возвращается назад.
    """

    __slots__ = ("_tokens", "_index", "_depth", "_max_depth")

    def __init__(self, tokens: list[Token], max_depth: int = MAX_DEPTH) -> None:
        self._tokens = tokens
        self._index = 0
        self._depth = 0
        self._max_depth = max_depth

    def parse(self) -> Node:
        node = self._parse_expression()

        # Без этой проверки строка "2 + 2)" разобралась бы успешно: парсер
        # прочитал бы "2 + 2", счёл работу выполненной и не заметил лишнюю
        # скобку.
        current = self._current
        if current.type is not TokenType.EOF:
            raise ExpressionSyntaxError(
                "Лишний текст после конца выражения", position=current.position
            )
        return node

    # --- Правила грамматики ---

    def _parse_expression(self) -> Node:
        node = self._parse_term()
        while self._current.type in ADDITIVE:
            token = self._advance()
            right = self._parse_term()
            node = BinaryOp(OPERATOR_BY_TOKEN[token.type], node, right, token.position)
        return node

    def _parse_term(self) -> Node:
        node = self._parse_factor()
        while self._current.type in MULTIPLICATIVE:
            token = self._advance()
            right = self._parse_factor()
            node = BinaryOp(OPERATOR_BY_TOKEN[token.type], node, right, token.position)
        return node

    def _parse_factor(self) -> Node:
        self._depth += 1
        if self._depth > self._max_depth:
            raise DepthExceededError(
                f"Вложенность глубже {self._max_depth} уровней",
                position=self._current.position,
            )
        try:
            return self._parse_factor_body()
        finally:
            self._depth -= 1

    def _parse_factor_body(self) -> Node:
        token = self._current

        if token.type is TokenType.NUMBER:
            self._advance()
            assert token.value is not None
            return Number(token.value, token.position)

        if token.type in ADDITIVE:
            # Правило рекурсивно, поэтому "--5" разбирается как -(-5).
            # Унарный плюс добавлен для симметрии: "+5" — допустимая запись.
            self._advance()
            operand = self._parse_factor()
            return UnaryOp(OPERATOR_BY_TOKEN[token.type], operand, token.position)

        if token.type is TokenType.LPAREN:
            self._advance()
            # Возврат на верхний уровень грамматики: внутри скобок снова
            # доступны все операции, а вложенность работает на любую глубину.
            node = self._parse_expression()
            if self._current.type is not TokenType.RPAREN:
                raise ExpressionSyntaxError(
                    "Не хватает закрывающей скобки", position=self._current.position
                )
            self._advance()
            return node

        if token.type is TokenType.RPAREN:
            raise ExpressionSyntaxError("Лишняя закрывающая скобка", position=token.position)

        if token.type is TokenType.EOF:
            raise ExpressionSyntaxError(
                "Выражение оборвано: ожидалось число или скобка", position=token.position
            )

        raise ExpressionSyntaxError("Ожидалось число или скобка", position=token.position)

    # --- Работа с потоком токенов ---

    @property
    def _current(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        # На EOF не сдвигаемся: он последний, и уход за границу списка
        # означал бы ошибку в самом парсере, а не в выражении.
        if token.type is not TokenType.EOF:
            self._index += 1
        return token
