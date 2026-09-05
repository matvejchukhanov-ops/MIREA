"""Обработчики команд.

Каждый принимает разобранный запрос и состояние соединения, возвращает то,
что попадёт в поле result ответа. О JSON, кадрах и сокетах обработчики
не знают ничего — этим занимаются слои выше.

Об ошибке сообщается исключением ProtocolError с кодом: превращать его
в ответ будет вызывающая сторона.

Этап 3: ping и quit. Команды calc и history появятся на этапах 4 и 6 —
до тех пор сервер честно отвечает на них UNKNOWN_COMMAND.
"""
from __future__ import annotations

from .dispatcher import Dispatcher
from .protocol import Request
from .session import Session


def handle_ping(request: Request, session: Session) -> str:
    """Проверка живости соединения."""
    return "pong"


def handle_quit(request: Request, session: Session) -> str:
    """Завершение сеанса по инициативе клиента."""
    # Соединение закрывается не здесь: сначала нужно отправить ответ.
    session.should_close = True
    return "bye"


def build_dispatcher() -> Dispatcher:
    """Собрать реестр команд.

    Вызывается один раз при запуске сервера. Реестр после сборки только
    читается, поэтому его безопасно делить между потоками.
    """
    dispatcher = Dispatcher()
    dispatcher.register("ping", handle_ping)
    dispatcher.register("quit", handle_quit)
    return dispatcher
