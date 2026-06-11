"""Start avatar render loop feeding an AgoraRTCPublisher."""
from __future__ import annotations

import asyncio
import threading
from typing import Optional

from src.server.agora.publisher import AgoraRTCPublisher
from src.utils.logging import logger


def _agora_worker(quit_event, loop, container, publisher: AgoraRTCPublisher, player: "AgoraHumanPlayer"):
    publisher.attach_notify(player.notify)
    try:
        container.render(quit_event, loop, None, None, media_sink=publisher)
    except Exception:
        logger.exception("AgoraHumanPlayer render thread failed")


class AgoraHumanPlayer:
    def __init__(self, avatar_stream, publisher: AgoraRTCPublisher):
        self._container = avatar_stream
        self._publisher = publisher
        self._thread: Optional[threading.Thread] = None
        self._thread_quit: Optional[threading.Event] = None

    def notify(self, eventpoint):
        if self._container is not None:
            self._container.notify(eventpoint)

    def start(self, loop: asyncio.AbstractEventLoop):
        if self._thread is not None:
            return
        self._thread_quit = threading.Event()
        self._thread = threading.Thread(
            name="agora-media-player",
            target=_agora_worker,
            args=(self._thread_quit, loop, self._container, self._publisher, self),
            daemon=True,
        )
        self._thread.start()
        logger.info("AgoraHumanPlayer worker started")

    def stop(self):
        if self._thread_quit is not None:
            self._thread_quit.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._publisher.stop()
        self._container = None
