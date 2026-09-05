"""Тесты диспетчера и обработчиков команд.

Запуск:
    python -m unittest discover
"""
from __future__ import annotations

import unittest

from server.dispatcher import Dispatcher
from server.handlers import build_dispatcher
from server.protocol import ErrorCode, ProtocolError, Request
from server.session import Session


def make_request(cmd: str, **payload: object) -> Request:
    return Request(cmd=cmd, id=None, payload={"cmd": cmd, **payload})


class DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Session(peer="127.0.0.1:1234")

    def test_вызывает_зарегистрированный_обработчик(self) -> None:
        dispatcher = Dispatcher()
        dispatcher.register("double", lambda request, session: 42)
        self.assertEqual(dispatcher.dispatch(make_request("double"), self.session), 42)

    def test_обработчик_получает_запрос_и_сессию(self) -> None:
        seen: list[object] = []
        dispatcher = Dispatcher()
        dispatcher.register("spy", lambda request, session: seen.append((request, session)))
        dispatcher.dispatch(make_request("spy"), self.session)
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0][1], self.session)

    def test_неизвестная_команда(self) -> None:
        dispatcher = Dispatcher()
        dispatcher.register("ping", lambda request, session: "pong")
        with self.assertRaises(ProtocolError) as ctx:
            dispatcher.dispatch(make_request("нет такой"), self.session)
        self.assertEqual(ctx.exception.code, ErrorCode.UNKNOWN_COMMAND)

    def test_сообщение_перечисляет_доступные_команды(self) -> None:
        # Иначе клиенту негде узнать, что вообще поддерживается.
        dispatcher = Dispatcher()
        dispatcher.register("ping", lambda request, session: "pong")
        with self.assertRaises(ProtocolError) as ctx:
            dispatcher.dispatch(make_request("wat"), self.session)
        self.assertIn("ping", ctx.exception.message)

    def test_повторная_регистрация_запрещена(self) -> None:
        # Тихая перезапись означала бы, что часть команд молча перестала
        # работать. Лучше упасть при запуске сервера.
        dispatcher = Dispatcher()
        dispatcher.register("ping", lambda request, session: "pong")
        with self.assertRaises(ValueError):
            dispatcher.register("ping", lambda request, session: "другое")


class HandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dispatcher = build_dispatcher()
        self.session = Session(peer="127.0.0.1:1234")

    def test_ping_отвечает_pong(self) -> None:
        self.assertEqual(self.dispatcher.dispatch(make_request("ping"), self.session), "pong")

    def test_ping_не_закрывает_соединение(self) -> None:
        self.dispatcher.dispatch(make_request("ping"), self.session)
        self.assertFalse(self.session.should_close)

    def test_quit_прощается_и_помечает_сессию(self) -> None:
        result = self.dispatcher.dispatch(make_request("quit"), self.session)
        self.assertEqual(result, "bye")
        # Соединение закрывает цикл обмена — после того, как ответ отправлен.
        self.assertTrue(self.session.should_close)

    def test_зарегистрированы_все_команды_протокола(self) -> None:
        self.assertEqual(self.dispatcher.commands, ["calc", "history", "ping", "quit"])

    def test_calc_считает(self) -> None:
        self.assertEqual(
            self.dispatcher.dispatch(make_request("calc", expr="2+3*4"), self.session), 14
        )

    def test_calc_без_выражения(self) -> None:
        with self.assertRaises(ProtocolError) as ctx:
            self.dispatcher.dispatch(make_request("calc"), self.session)
        self.assertEqual(ctx.exception.code, ErrorCode.BAD_REQUEST)

    def test_ошибка_вычисления_превращается_в_код_протокола(self) -> None:
        with self.assertRaises(ProtocolError) as ctx:
            self.dispatcher.dispatch(make_request("calc", expr="1/0"), self.session)
        self.assertEqual(ctx.exception.code, ErrorCode.DIV_BY_ZERO)

    def test_позиция_ошибки_доходит_до_протокола(self) -> None:
        with self.assertRaises(ProtocolError) as ctx:
            self.dispatcher.dispatch(make_request("calc", expr="2 + $"), self.session)
        self.assertEqual(ctx.exception.code, ErrorCode.UNKNOWN_CHAR)
        self.assertEqual(ctx.exception.position, 4)

    def test_история_накапливается(self) -> None:
        self.dispatcher.dispatch(make_request("calc", expr="2+2"), self.session)
        self.dispatcher.dispatch(make_request("calc", expr="10/4"), self.session)
        history = self.dispatcher.dispatch(make_request("history"), self.session)
        self.assertEqual(
            history, [{"expr": "2+2", "result": 4}, {"expr": "10/4", "result": 2.5}]
        )

    def test_неудачное_вычисление_в_историю_не_попадает(self) -> None:
        with self.assertRaises(ProtocolError):
            self.dispatcher.dispatch(make_request("calc", expr="1/0"), self.session)
        self.assertEqual(self.dispatcher.dispatch(make_request("history"), self.session), [])

    def test_история_ограничена_запрошенным_числом(self) -> None:
        for number in range(5):
            self.dispatcher.dispatch(make_request("calc", expr=str(number)), self.session)
        history = self.dispatcher.dispatch(make_request("history", limit=2), self.session)
        # Последние по времени, в хронологическом порядке.
        self.assertEqual([item["expr"] for item in history], ["3", "4"])

    def test_история_отдельна_у_каждого_соединения(self) -> None:
        other = Session(peer="127.0.0.1:9999")
        self.dispatcher.dispatch(make_request("calc", expr="2+2"), self.session)
        self.assertEqual(self.dispatcher.dispatch(make_request("history"), other), [])


if __name__ == "__main__":
    unittest.main()
