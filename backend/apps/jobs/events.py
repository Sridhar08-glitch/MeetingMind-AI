"""A tiny in-process event bus.

The engine publishes lifecycle events (job/stage started, completed, failed…).
Other modules subscribe without the engine knowing about them — the seam that
lets us bolt on notifications, metrics sinks, or a meetings-timeline bridge later
without touching engine code.

In eager mode this is synchronous; with a real broker the same publish points
still fire from the worker process. Subscribers must be side-effect-safe and must
never raise back into the engine.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable

logger = logging.getLogger("meetingmind.processing")

# A handler receives (event_name, payload_dict).
Handler = Callable[[str, dict], None]

WILDCARD = "*"


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        self._subscribers[event].append(handler)

    def publish(self, event: str, **payload) -> None:
        for handler in [*self._subscribers.get(event, []), *self._subscribers.get(WILDCARD, [])]:
            try:
                handler(event, payload)
            except Exception:  # noqa: BLE001 — a bad subscriber must not break the engine
                logger.exception("Event subscriber failed for %s", event)

    def clear(self) -> None:
        self._subscribers.clear()


# Process-wide default bus.
event_bus = EventBus()
