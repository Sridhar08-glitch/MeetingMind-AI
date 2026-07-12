"""LiveMeetingConsumer — receives audio chunks over a WebSocket, streams back a
near-real-time transcript (+ translation + throttled AI preview), and on Stop
finalizes into a real Meeting that runs the EXISTING pipeline.

Only lightweight info is streamed continuously; expensive AI is throttled, and
Knowledge/Workspace/Executive materialization happens once at finalize (not per
chunk) — via the reused JOB_COMPLETED subscribers.
"""
from __future__ import annotations

import json
import logging
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.meetings.live import service

logger = logging.getLogger("meetingmind.processing")

_AI_THROTTLE_SECONDS = 25.0
_TX_THROTTLE_SECONDS = 4.0


class LiveMeetingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close(code=4001)
            return
        self.user = user
        self.session = None
        self._last_tx = 0.0
        self._last_ai = 0.0
        await self.accept()

    async def disconnect(self, code):
        # If the client drops mid-recording (e.g. navigated away), auto-finalize so
        # the recording is queued as a meeting rather than lost. Idempotent: a real
        # Stop already finalized, so this becomes a no-op.
        if self.session is not None:
            try:
                await database_sync_to_async(service.finalize_on_disconnect, thread_sensitive=False)(self.session)
            except Exception:  # noqa: BLE001
                pass

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            await self._on_chunk(bytes_data)
            return
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
        except json.JSONDecodeError:
            return
        t = msg.get("type")
        if t == "start":
            await self._start(msg)
        elif t == "pause":
            await self._set_status("paused")
        elif t == "resume":
            await self._set_status("recording")
        elif t == "stop":
            await self._stop()

    # --- control ---------------------------------------------------------
    async def _start(self, msg: dict):
        self.session = await database_sync_to_async(service.create_session)(
            self.user,
            source=msg.get("source", ""),
            media_kind=msg.get("media_kind", "audio"),
            title=msg.get("title", ""),
            meeting_language=msg.get("meeting_language", ""),
            transcript_language=msg.get("transcript_language", "original"),
            ai_language=msg.get("ai_language", ""),
            file_extension=msg.get("file_extension", "webm"),
        )
        await self._send({"type": "started", "session_id": str(self.session.id)})

    async def _set_status(self, status: str):
        if self.session is not None:
            await database_sync_to_async(service.set_status)(self.session, status)
        await self._send({"type": "status", "status": status})

    async def _stop(self):
        if self.session is None:
            await self._send({"type": "error", "message": "No active recording."})
            return
        await self._send({"type": "finalizing"})
        # One last transcription pass so the preview is as complete as possible.
        try:
            await database_sync_to_async(service.transcribe_new, thread_sensitive=False)(self.session)
        except Exception:  # noqa: BLE001
            pass
        try:
            meeting = await database_sync_to_async(service.finalize, thread_sensitive=False)(self.session, actor=self.user)
            await self._send({"type": "completed", "meeting_id": str(meeting.id)})
        except Exception as exc:  # noqa: BLE001
            await self._send({"type": "error", "message": f"Finalize failed: {exc}"})

    # --- audio -----------------------------------------------------------
    async def _on_chunk(self, data: bytes):
        if self.session is None:
            return
        await database_sync_to_async(service.append_chunk)(self.session, data)
        # Throttle transcription cadence; run it inline (awaited) so incoming
        # chunks simply queue while a pass is in flight — no untracked tasks.
        now = time.monotonic()
        if now - self._last_tx < _TX_THROTTLE_SECONDS:
            return
        self._last_tx = now
        await self._transcribe()

    async def _transcribe(self):
        try:
            # Heavy (ffmpeg + Whisper) → run OFF the shared thread-sensitive
            # executor so it never blocks the consumer's control/DB path.
            rows = await database_sync_to_async(service.transcribe_new, thread_sensitive=False)(self.session)
            if rows:
                await self._send({"type": "transcript", "segments": rows})
                await self._maybe_ai()
        except Exception:  # noqa: BLE001 — preview only
            logger.debug("Live transcription task failed", exc_info=True)

    async def _maybe_ai(self):
        now = time.monotonic()
        if now - self._last_ai < _AI_THROTTLE_SECONDS:
            return
        self._last_ai = now
        live = await database_sync_to_async(service.update_live_ai, thread_sensitive=False)(self.session)
        if live:
            await self._send({"type": "ai", "ai": live})

    async def _send(self, obj: dict):
        await self.send(text_data=json.dumps(obj))
