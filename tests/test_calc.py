"""Тесты вычислительного ядра.

Сети здесь нет вообще: проверяется чистая функция «строка → число».
Именно ради этого calc/ не знает о сокетах — иначе отладка парсера
смешалась бы с отладкой сети.

Запуск:
    python -m unittest discover
"""
from __future__ import annotations

import unittest

from server.calc import (
    DepthExceededError,
    DivisionByZeroError,
    ExpressionSyntaxError,
    ExpressionTooLongError,
    NumberTooLargeError,
    UnknownCharError,
    calculate,
)
from server.calc.lexer import TokenType, tokenize


class LexerTests(unittest.TestCase):
    def test_разбивает_на_токены(self) -> None:
        types = [token.type for token in tokenize("2+3")]
        self.assertEqual(
            types, [TokenType.NUMBER, TokenType.PLUS, TokenType.NUMBER, TokenType.EOF]
        )

    def test_пробелы_не_влияют(self) -> None:
        self.assertEqual(
            [t.type for t in tokenize("2+2")], [t.type for t in tokenize("  2  +  2  ")]
        )

    def test_позиции_сохраняются(self) -> None:
        tokens = tokenize("12 + 3")
        self.assertEqual(tokens[0].position, 0)
        self.assertEqual(tokens[1].position, 3)
        self.assertEqual(tokens[2].position, 5)

    def test_целое_и_дробное(self) -> None:
        self.assertEqual(tokenize("42")[0].value, 42)
        self.assertEqual(tokenize("3.5")[0].value, 3.5)

    def test_недопустимый_символ(self) -> None:
        with self.assertRaises(UnknownCharError) as ctx:
            tokenize("2 $ 3")
        self.assertEqual(ctx.exception.position, 2)

    def test_две_точки_в_числе(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            tokenize("1.2.3")

    def test_точка_без_дробной_части(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            tokenize("5.")

    def test_нелатинские_цифры_не_считаются_цифрами(self) -> None:
        # str.isdigit() принял бы арабскую цифру, int() тоже, а float() —
        # нет. Такое расхождение даёт трудноуловимые ошибки, поэтому набор
        # цифр задан явно.
        with self.assertRaises(UnknownCharError):
            tokenize("٣ + 1")


class ArithmeticTests(unittest.TestCase):
    def test_сложение(self) -> None:
        self.assertEqual(calculate("2+2"), 4)

    def test_вычитание(self) -> None:
        self.assertEqual(calculate("10-3"), 7)

    def test_умножение(self) -> None:
        self.assertEqual(calculate("6*7"), 42)

    def test_деление(self) -> None:
        self.assertEqual(calculate("8/2"), 4)

    def test_одно_число(self) -> None:
        self.assertEqual(calculate("42"), 42)

    def test_цепочка_операций(self) -> None:
        self.assertEqual(calculate("1+2+3+4+5"), 15)

    def test_вычитание_левоассоциативно(self) -> None:
        # (10-3)-2 = 5, а не 10-(3-2) = 9.
        self.assertEqual(calculate("10-3-2"), 5)

    def test_деление_левоассоциативно(self) -> None:
        self.assertEqual(calculate("100/10/2"), 5)


class PriorityTests(unittest.TestCase):
    """Приоритет не запрограммирован — он следует из структуры грамматики."""

    def test_умножение_раньше_сложения(self) -> None:
        self.assertEqual(calculate("2+3*4"), 14)

    def test_умножение_раньше_сложения_слева(self) -> None:
        self.assertEqual(calculate("2*3+4"), 10)

    def test_деление_раньше_вычитания(self) -> None:
        self.assertEqual(calculate("10-8/2"), 6)

    def test_скобки_меняют_порядок(self) -> None:
        self.assertEqual(calculate("(2+3)*4"), 20)

    def test_вложенные_скобки(self) -> None:
        self.assertEqual(calculate("((2+3)*(4-1))/5"), 3)

    def test_глубокая_но_допустимая_вложенность(self) -> None:
        self.assertEqual(calculate("(" * 40 + "7" + ")" * 40), 7)


class UnaryTests(unittest.TestCase):
    def test_унарный_минус(self) -> None:
        self.assertEqual(calculate("-5"), -5)

    def test_унарный_плюс(self) -> None:
        self.assertEqual(calculate("+5"), 5)

    def test_минус_перед_скобкой(self) -> None:
        self.assertEqual(calculate("-(2+3)"), -5)

    def test_двойной_минус(self) -> None:
        # Правило рекурсивно, поэтому --5 разбирается как -(-5).
        self.assertEqual(calculate("--5"), 5)

    def test_минус_после_операции(self) -> None:
        self.assertEqual(calculate("2*-3"), -6)

    def test_минус_и_приоритет(self) -> None:
        # -(2*3), а не (-2)*3 — результат тот же, но дерево разное.
        self.assertEqual(calculate("-2*3"), -6)


class NumberTypeTests(unittest.TestCase):
    def test_целое_деление_даёт_целое(self) -> None:
        result = calculate("4/2")
        self.assertEqual(result, 2)
        self.assertIsInstance(result, int)

    def test_дробное_деление_даёт_дробное(self) -> None:
        result = calculate("5/2")
        self.assertEqual(result, 2.5)
        self.assertIsInstance(result, float)

    def test_дробные_слагаемые(self) -> None:
        self.assertEqual(calculate("0.5+0.25"), 0.75)

    def test_дробный_результат_приводится_к_целому(self) -> None:
        self.assertIsInstance(calculate("1.5+1.5"), int)


class ErrorTests(unittest.TestCase):
    def test_деление_на_ноль(self) -> None:
        with self.assertRaises(DivisionByZeroError):
            calculate("10/0")

    def test_деление_на_вычисленный_ноль(self) -> None:
        with self.assertRaises(DivisionByZeroError):
            calculate("1/(3-3)")

    def test_оператор_без_операнда(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("2 + * 3")

    def test_не_хватает_закрывающей_скобки(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("(2+3")

    def test_лишняя_закрывающая_скобка(self) -> None:
        # Без проверки на конец разбора это выражение прошло бы: парсер
        # прочитал бы "2+2" и счёл работу выполненной.
        with self.assertRaises(ExpressionSyntaxError):
            calculate("2+2)")

    def test_пустые_скобки(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("()")

    def test_пустое_выражение(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("")

    def test_только_пробелы(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("   ")

    def test_оборванное_выражение(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("2 +")

    def test_два_числа_подряд(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            calculate("2 3")

    def test_недопустимый_символ(self) -> None:
        with self.assertRaises(UnknownCharError):
            calculate("2 @ 3")

    def test_знакомый_символ_не_на_месте(self) -> None:
        # Звёздочка сама по себе допустима, поэтому это синтаксическая
        # ошибка, а не неизвестный символ. Разница видна клиенту в коде.
        with self.assertRaises(ExpressionSyntaxError):
            calculate("2 ** 3")

    def test_позиция_указывает_на_ошибку(self) -> None:
        with self.assertRaises(UnknownCharError) as ctx:
            calculate("12 + $")
        self.assertEqual(ctx.exception.position, 5)


class LimitTests(unittest.TestCase):
    """Данные приходят из сети: каждое ограничение закрывает способ атаки."""

    def test_слишком_длинное_выражение(self) -> None:
        with self.assertRaises(ExpressionTooLongError):
            calculate("1+" * 600 + "1")

    def test_слишком_глубокая_вложенность(self) -> None:
        # Без этой защиты строка из тысячи скобок переполнила бы стек
        # рекурсивного парсера, и падение выглядело бы необъяснимо.
        with self.assertRaises(DepthExceededError):
            calculate("(" * 100 + "1" + ")" * 100)

    def test_слишком_длинная_запись_числа(self) -> None:
        with self.assertRaises(NumberTooLargeError):
            calculate("9" * 200)

    def test_слишком_большой_результат(self) -> None:
        # Целые в Python неограниченны, поэтому произведение больших чисел
        # надолго заняло бы процессор — способ положить сервер короткой строкой.
        huge = "9" * 100
        with self.assertRaises(NumberTooLargeError):
            calculate(" * ".join([huge] * 4))

    def test_переполнение_дробного(self) -> None:
        # У чисел с плавающей точкой переполнение даёт бесконечность,
        # а не исключение: без проверки клиент получил бы "Infinity".
        large_float = "9" * 97 + ".5"
        with self.assertRaises(NumberTooLargeError):
            calculate(" * ".join([large_float] * 4))


class SecurityTests(unittest.TestCase):
    """Проверка того, ради чего отвергнут eval()."""

    def test_код_python_не_выполняется(self) -> None:
        # С eval() эта строка выполнила бы импорт и запуск процесса.
        with self.assertRaises(UnknownCharError):
            calculate("__import__('os').system('echo hacked')")

    def test_имена_не_распознаются(self) -> None:
        with self.assertRaises(UnknownCharError):
            calculate("open")

    def test_возведение_в_степень_не_поддерживается(self) -> None:
        # 9**9**9 в eval() заняло бы процессор надолго. Здесь выражение
        # просто не соответствует грамматике.
        with self.assertRaises(ExpressionSyntaxError):
            calculate("9**9**9")


if __name__ == "__main__":
    unittest.main()
