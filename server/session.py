"""Состояние одного соединения.

Живёт в потоке, который обслуживает клиента, и умирает вместе с ним. Общего
с другими соединениями здесь ничего нет — именно поэтому появление потоков
почти ничего не потребовало синхронизировать.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

# Сколько вычислений помнить. Ограничение обязательно: без него клиент,
# считающий выражения часами, незаметно съедает память сервера.
# deque с maxlen вытесняет старые записи сам.
HISTORY_CAPACITY = 50


@dataclass(slots=True)
class Session:
    """Что сервер помнит о клиенте, пока тот подключён."""

    peer: str

    # Обработчик команды не закрывает соединение сам: ответ нужно сначала
    # отправить. Он лишь поднимает флаг, а цикл обмена завершается после
    # того, как ответ ушёл.
    should_close: bool = False

    history: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=HISTORY_CAPACITY)
    )

    def remember(self, expression: str, result: int | float) -> None:
        """Записать успешное вычисление."""
        self.history.append({"expr": expression, "result": result})

    def recent(self, limit: int) -> list[dict[str, Any]]:
        """Последние вычисления в хронологическом порядке."""
        if limit <= 0:
            return []
        return list(self.history)[-limit:]
