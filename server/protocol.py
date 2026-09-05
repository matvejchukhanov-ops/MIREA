"""Разбор запросов и сборка ответов.

Слой между кадрами и командами: сюда приходят байты кадра, отсюда уходят
готовые к отправке кадры ответа. Обработчики команд про JSON ничего не знают —
они принимают Request и возвращают результат.

Формат зафиксирован в docs/protocol.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from common.framing import encode_frame


class ErrorCode(StrEnum):
    """Машиночитаемые коды ошибок.

    Клиент принимает решения по коду, человек читает message. Разбирать
    текст сообщения в клиенте нельзя: формулировки меняются, коды — нет.
    """

    BAD_JSON = "BAD_JSON"
    BAD_REQUEST = "BAD_REQUEST"
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    EXPR_TOO_LONG = "EXPR_TOO_LONG"
    UNKNOWN_CHAR = "UNKNOWN_CHAR"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"
    DIV_BY_ZERO = "DIV_BY_ZERO"
    NUMBER_TOO_LARGE = "NUMBER_TOO_LARGE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    FRAME_TOO_LONG = "FRAME_TOO_LONG"
    SERVER_BUSY = "SERVER_BUSY"


class ProtocolError(Exception):
    """Ошибка, о которой нужно сообщить клиенту кодом из ErrorCode."""

    def __init__(self, code: ErrorCode, message: str, *, position: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.position = position


@dataclass(frozen=True, slots=True)
class Request:
    """Разобранный запрос клиента."""

    cmd: str
    id: str | int | None
    payload: dict[str, Any]

    def require_str(self, name: str) -> str:
        """Достать обязательный строковый аргумент."""
        value = self.payload.get(name)
        if value is None:
            raise ProtocolError(
                ErrorCode.BAD_REQUEST, f"Команда {self.cmd!r} требует поля {name!r}"
            )
        if not isinstance(value, str):
            raise ProtocolError(ErrorCode.BAD_REQUEST, f"Поле {name!r} должно быть строкой")
        return value

    def optional_int(self, name: str, default: int, *, minimum: int, maximum: int) -> int:
        """Достать необязательный целочисленный аргумент с проверкой границ."""
        value = self.payload.get(name)
        if value is None:
            return default
        # bool в Python — подкласс int, и True прошёл бы проверку как единица.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError(ErrorCode.BAD_REQUEST, f"Поле {name!r} должно быть целым числом")
        if not minimum <= value <= maximum:
            raise ProtocolError(
                ErrorCode.BAD_REQUEST,
                f"Поле {name!r} должно быть в диапазоне {minimum}-{maximum}, получено {value}",
            )
        return value


def parse_request(frame: bytes) -> Request:
    """Разобрать кадр в запрос.

    Данные пришли из сети, поэтому проверяется всё: кодировка, разбираемость
    JSON, тип верхнего уровня, наличие и тип обязательных полей.
    """
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError(ErrorCode.BAD_JSON, "Сообщение не в кодировке UTF-8") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(
            ErrorCode.BAD_JSON, f"Не удалось разобрать JSON: {exc.msg}", position=exc.pos
        ) from exc

    if not isinstance(data, dict):
        raise ProtocolError(ErrorCode.BAD_JSON, "Ожидался объект JSON")

    cmd = data.get("cmd")
    if cmd is None:
        raise ProtocolError(ErrorCode.BAD_REQUEST, "Поле 'cmd' обязательно")
    if not isinstance(cmd, str) or not cmd:
        raise ProtocolError(ErrorCode.BAD_REQUEST, "Поле 'cmd' должно быть непустой строкой")

    request_id = data.get("id")
    if request_id is not None and not isinstance(request_id, (str, int)):
        raise ProtocolError(ErrorCode.BAD_REQUEST, "Поле 'id' должно быть строкой или числом")
    if isinstance(request_id, bool):
        raise ProtocolError(ErrorCode.BAD_REQUEST, "Поле 'id' должно быть строкой или числом")

    return Request(cmd=cmd, id=request_id, payload=data)


def success_frame(result: Any, request_id: str | int | None = None) -> bytes:
    """Собрать кадр успешного ответа."""
    payload: dict[str, Any] = {"status": "ok", "result": result}
    if request_id is not None:
        payload["id"] = request_id
    return _serialize(payload)


def error_frame(
    code: ErrorCode,
    message: str,
    request_id: str | int | None = None,
    position: int | None = None,
) -> bytes:
    """Собрать кадр ответа с ошибкой."""
    payload: dict[str, Any] = {"status": "error", "code": str(code), "message": message}
    if request_id is not None:
        payload["id"] = request_id
    if position is not None:
        payload["position"] = position
    return _serialize(payload)


def _serialize(payload: dict[str, Any]) -> bytes:
    # ensure_ascii=False оставляет кириллицу читаемой в логах и в telnet.
    # Переводы строк внутри значений json экранирует сам, поэтому кадр
    # гарантированно останется однострочным.
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return encode_frame(text.encode("utf-8"))
