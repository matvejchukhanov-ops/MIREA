"""Сквозные тесты: настоящие сокеты, настоящий сервер.

Юнит-тесты проверяют части по отдельности; здесь проверяется, что они
складываются в работающую систему. Сервер поднимается в отдельном потоке
на свободном порту, клиенты подключаются через реальный TCP.

Запуск:
    python -m unittest discover
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
import unittest

from common.framing import FrameReader, encode_frame
from server.config import ServerConfig
from server.tcp_server import TCPServer

CONNECT_TIMEOUT = 5.0


def free_port() -> int:
    """Занять и сразу отпустить порт, чтобы узнать свободный номер."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Peer:
    """Минимальный клиент протокола для тестов."""

    def __init__(self, host: str, port: int) -> None:
        self._sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        self._sock.settimeout(CONNECT_TIMEOUT)
        self._reader = FrameReader()
        self._ready: list[bytes] = []

    def send_raw(self, data: bytes) -> None:
        self._sock.sendall(data)

    def send(self, request: dict) -> None:
        self.send_raw(encode_frame(json.dumps(request, ensure_ascii=False).encode("utf-8")))

    def receive(self) -> dict:
        while not self._ready:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("сервер закрыл соединение")
            self._ready.extend(self._reader.feed(chunk))
        return json.loads(self._ready.pop(0).decode("utf-8"))

    def ask(self, request: dict) -> dict:
        self.send(request)
        return self.receive()

    def server_closed(self) -> bool:
        try:
            return self._sock.recv(4096) == b""
        except OSError:
            return False

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "Peer":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ServerTestCase(unittest.TestCase):
    """Поднимает сервер на время теста."""

    max_connections = 64

    def setUp(self) -> None:
        # Сервер намеренно пишет в лог предупреждения об отказах и нарушениях
        # протокола. В выводе тестов они выглядели бы как сбои, хотя это
        # ожидаемое поведение, которое тесты и проверяют.
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        self.port = free_port()
        self.config = ServerConfig(
            host="127.0.0.1",
            port=self.port,
            max_connections=self.max_connections,
            log_level="ERROR",
        )
        self.server = TCPServer(self.config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._wait_until_listening()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)

    def connect(self) -> Peer:
        return Peer("127.0.0.1", self.port)

    def _wait_until_listening(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.02)
        self.fail("Сервер не начал слушать порт")


class ProtocolOverSocketTests(ServerTestCase):
    def test_ping(self) -> None:
        with self.connect() as peer:
            self.assertEqual(peer.ask({"cmd": "ping"}), {"status": "ok", "result": "pong"})

    def test_вычисление(self) -> None:
        with self.connect() as peer:
            self.assertEqual(peer.ask({"cmd": "calc", "expr": "2 + 3 * 4"})["result"], 14)

    def test_идентификатор_возвращается(self) -> None:
        with self.connect() as peer:
            self.assertEqual(peer.ask({"cmd": "calc", "expr": "1+1", "id": "x"})["id"], "x")

    def test_ошибка_не_рвёт_соединение(self) -> None:
        with self.connect() as peer:
            reply = peer.ask({"cmd": "calc", "expr": "1/0"})
            self.assertEqual(reply["code"], "DIV_BY_ZERO")
            # Соединение обязано пережить ошибку в данных клиента.
            self.assertEqual(peer.ask({"cmd": "ping"})["result"], "pong")

    def test_позиция_ошибки_доходит_до_клиента(self) -> None:
        with self.connect() as peer:
            reply = peer.ask({"cmd": "calc", "expr": "12 + $"})
            self.assertEqual(reply["code"], "UNKNOWN_CHAR")
            self.assertEqual(reply["position"], 5)

    def test_история_в_пределах_соединения(self) -> None:
        with self.connect() as peer:
            peer.ask({"cmd": "calc", "expr": "2+2"})
            peer.ask({"cmd": "calc", "expr": "10/4"})
            history = peer.ask({"cmd": "history"})["result"]
            self.assertEqual([item["expr"] for item in history], ["2+2", "10/4"])

    def test_история_нового_соединения_пуста(self) -> None:
        with self.connect() as first:
            first.ask({"cmd": "calc", "expr": "2+2"})
        with self.connect() as second:
            self.assertEqual(second.ask({"cmd": "history"})["result"], [])

    def test_конвейер_из_двух_запросов(self) -> None:
        with self.connect() as peer:
            peer.send_raw(
                encode_frame(b'{"cmd":"calc","expr":"1+1","id":1}')
                + encode_frame(b'{"cmd":"calc","expr":"2+2","id":2}')
            )
            first, second = peer.receive(), peer.receive()
            self.assertEqual((first["id"], first["result"]), (1, 2))
            self.assertEqual((second["id"], second["result"]), (2, 4))

    def test_quit_закрывает_соединение(self) -> None:
        with self.connect() as peer:
            self.assertEqual(peer.ask({"cmd": "quit"})["result"], "bye")
            self.assertTrue(peer.server_closed())

    def test_превышение_кадра(self) -> None:
        with self.connect() as peer:
            peer.send_raw(b"x" * 5000)
            self.assertEqual(peer.receive()["code"], "FRAME_TOO_LONG")
            self.assertTrue(peer.server_closed())

    def test_сервер_жив_после_нарушений(self) -> None:
        with self.connect() as peer:
            peer.send_raw(b"x" * 5000)
            peer.receive()
        with self.connect() as peer:
            self.assertEqual(peer.ask({"cmd": "ping"})["result"], "pong")


class ConcurrencyTests(ServerTestCase):
    """Проверка того, ради чего появились потоки."""

    def test_несколько_клиентов_одновременно(self) -> None:
        count = 5
        peers = [self.connect() for _ in range(count)]
        try:
            # Все подключены и никто ещё не отключился: одному потоку такое
            # не под силу — он завис бы на первом клиенте.
            deadline = time.monotonic() + 5
            while self.server.active_connections < count and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(self.server.active_connections, count)

            for index, peer in enumerate(peers):
                self.assertEqual(peer.ask({"cmd": "calc", "expr": f"{index}+1"})["result"], index + 1)
        finally:
            for peer in peers:
                peer.close()

    def test_история_у_клиентов_не_смешивается(self) -> None:
        with self.connect() as first, self.connect() as second:
            first.ask({"cmd": "calc", "expr": "1+1"})
            second.ask({"cmd": "calc", "expr": "2+2"})
            self.assertEqual(
                [item["expr"] for item in first.ask({"cmd": "history"})["result"]], ["1+1"]
            )
            self.assertEqual(
                [item["expr"] for item in second.ask({"cmd": "history"})["result"]], ["2+2"]
            )

    def test_параллельные_вычисления_не_мешают_друг_другу(self) -> None:
        results: dict[int, object] = {}
        barrier = threading.Barrier(4)

        def worker(number: int) -> None:
            with self.connect() as peer:
                barrier.wait(timeout=5)
                results[number] = peer.ask({"cmd": "calc", "expr": f"{number} * 1000"})["result"]

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(1, 4)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(results, {1: 1000, 2: 2000, 3: 3000})


class ConnectionLimitTests(ServerTestCase):
    max_connections = 2

    def test_лишний_клиент_получает_внятный_отказ(self) -> None:
        # Молчаливый разрыв выглядел бы для клиента как поломка сети.
        held = [self.connect() for _ in range(2)]
        try:
            deadline = time.monotonic() + 5
            while self.server.active_connections < 2 and time.monotonic() < deadline:
                time.sleep(0.02)

            with self.connect() as extra:
                reply = extra.receive()
                self.assertEqual(reply["status"], "error")
                self.assertEqual(reply["code"], "SERVER_BUSY")

            # Освободилось место — новый клиент обслуживается.
            held.pop().close()
            deadline = time.monotonic() + 5
            while self.server.active_connections >= 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            with self.connect() as peer:
                self.assertEqual(peer.ask({"cmd": "ping"})["result"], "pong")
        finally:
            for peer in held:
                peer.close()


if __name__ == "__main__":
    unittest.main()
