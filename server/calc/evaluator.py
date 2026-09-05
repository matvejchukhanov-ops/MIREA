"""Вычислитель: дерево разбора в число.

Обход снизу вверх: сначала считаются листья, потом узлы над ними. Именно
поэтому приоритет операций получается сам собой — умножение лежит в дереве
глубже сложения.
"""
from __future__ import annotations

import math

from .errors import DivisionByZeroError, NumberTooLargeError
from .parser import BinaryOp, Node, Number, UnaryOp

# Предел величины промежуточного и конечного результата. Целые в Python
# неограниченны, поэтому без проверки выражение вида 99...9 * 99...9 * ...
# заняло бы процессор надолго — то есть стало бы способом положить сервер
# одной короткой строкой.
MAX_MAGNITUDE = 10**308

# За этой границей числа с плавающей точкой перестают различать соседние
# целые, и превращение в int теряет смысл.
EXACT_INTEGER_LIMIT = 2**53


def evaluate(node: Node) -> int | float:
    """Вычислить дерево разбора."""
    return _normalize(_evaluate(node))


def _evaluate(node: Node) -> int | float:
    if isinstance(node, Number):
        return node.value

    if isinstance(node, UnaryOp):
        value = _evaluate(node.operand)
        return -value if node.operator == "-" else value

    if isinstance(node, BinaryOp):
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        return _apply(node.operator, left, right, node.position)

    # Сюда можно попасть только при ошибке в самом парсере.
    raise TypeError(f"Неизвестный узел дерева: {node!r}")


def _apply(operator: str, left: int | float, right: int | float, position: int) -> int | float:
    if operator == "/":
        # Проверка до операции, а не после: ловить ZeroDivisionError означало
        # бы полагаться на то, что деление вообще дойдёт до выполнения.
        if right == 0:
            raise DivisionByZeroError("Деление на ноль", position=position)

    try:
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        elif operator == "/":
            result = left / right
        else:
            raise TypeError(f"Неизвестная операция: {operator!r}")
    except OverflowError as exc:
        # Возникает, например, при делении очень большого целого на дробь:
        # промежуточное преобразование в float не помещается в диапазон.
        raise NumberTooLargeError("Результат вне допустимого диапазона", position=position) from exc

    _check_magnitude(result, position)
    return result


def _check_magnitude(value: int | float, position: int) -> None:
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            raise NumberTooLargeError("Результат вне допустимого диапазона", position=position)
    elif abs(value) > MAX_MAGNITUDE:
        raise NumberTooLargeError("Результат слишком велик", position=position)


def _normalize(value: int | float) -> int | float:
    """Привести целый по значению результат к целому типу.

    Деление в Python всегда даёт число с плавающей точкой, поэтому 4 / 2
    вернуло бы 2.0. Человеку удобнее видеть 2, а 5 / 2 — по-прежнему 2.5.
    """
    if isinstance(value, float) and value.is_integer() and abs(value) < EXACT_INTEGER_LIMIT:
        return int(value)
    return value
