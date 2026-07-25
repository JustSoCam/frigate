"""Face enrichment for events created by external camera-side detection."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from urllib.request import urlopen

import cv2
import numpy as np

if TYPE_CHECKING:
    from .face import FaceRealTimeProcessor

logger = logging.getLogger(__name__)

GO2RTC_FRAME_ENDPOINT = "http://127.0.0.1:1984/api/frame.jpeg"
MAX_FRAME_BYTES = 16 * 1024 * 1024
CAPTURE_TIMEOUT = 8
CAPTURE_ATTEMPTS = 6
CAPTURE_INTERVAL = 1.5


def capture_go2rtc_frame(stream_name: str) -> bytes | None:
    """Capture one JPEG from an existing local go2rtc restream."""
    url = f"{GO2RTC_FRAME_ENDPOINT}?{urlencode({'src': stream_name})}"
    try:
        with urlopen(url, timeout=CAPTURE_TIMEOUT) as response:
            if response.status != 200:
                return None
            frame = bytes(response.read(MAX_FRAME_BYTES + 1))
    except OSError as error:
        logger.warning(
            "Unable to capture main-stream face frame for %s: %s",
            stream_name,
            error,
        )
        return None

    if not frame or len(frame) > MAX_FRAME_BYTES:
        logger.warning("Invalid main-stream face frame for %s", stream_name)
        return None
    return frame


@dataclass
class ExternalFaceEvent:
    event_id: str
    camera: str
    stream_name: str
    next_capture: float
    attempts: int = 0
    ended: bool = False


class ExternalFaceEnricher:
    """Capture main-stream frames without blocking the embeddings loop."""

    def __init__(
        self,
        face_processor: FaceRealTimeProcessor,
        capture_frame: Callable[[str], bytes | None] = capture_go2rtc_frame,
        executor: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.face_processor = face_processor
        self.capture_frame = capture_frame
        self.clock = clock
        self.executor = executor or ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="external_face_capture",
        )
        self._owns_executor = executor is None
        self.events: dict[str, ExternalFaceEvent] = {}
        self.futures: dict[str, Future[bytes | None]] = {}

    def start(self, event_id: str, camera: str, stream_name: str) -> None:
        """Begin face enrichment for an external person event."""
        self._finish(event_id, camera)
        self.events[event_id] = ExternalFaceEvent(
            event_id,
            camera,
            stream_name,
            self.clock(),
        )
        self._schedule_due(self.clock())

    def end(self, event_id: str, camera: str) -> None:
        """Stop retries while allowing an in-flight capture to complete."""
        event = self.events.get(event_id)
        if event is None:
            self.face_processor.expire_object(event_id, camera)
            return
        event.ended = True
        if event_id not in self.futures:
            self._finish(event_id, camera)

    def _finish(self, event_id: str, camera: str) -> None:
        """Discard an event and its recognition history."""
        self.events.pop(event_id, None)
        future = self.futures.pop(event_id, None)
        if future is not None:
            future.cancel()
        self.face_processor.expire_object(event_id, camera)

    def _process_completed(self, now: float) -> None:
        for event_id, future in list(self.futures.items()):
            if not future.done():
                continue

            self.futures.pop(event_id)
            event = self.events.get(event_id)
            if event is None:
                continue

            try:
                frame_bytes = future.result()
            except Exception:
                logger.exception(
                    "Main-stream face capture failed for %s",
                    event.camera,
                )
                frame_bytes = None

            recognized = False
            if frame_bytes:
                frame = cv2.imdecode(
                    np.frombuffer(frame_bytes, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if frame is not None:
                    recognized = self.face_processor.process_external_frame(
                        event.event_id,
                        event.camera,
                        frame,
                    )

            if recognized or event.ended or event.attempts >= CAPTURE_ATTEMPTS:
                self._finish(event.event_id, event.camera)
            else:
                event.next_capture = now + CAPTURE_INTERVAL

    def _schedule_due(self, now: float) -> None:
        for event_id, event in list(self.events.items()):
            if event.ended or event_id in self.futures or event.next_capture > now:
                continue
            event.attempts += 1
            self.futures[event_id] = self.executor.submit(
                self.capture_frame,
                event.stream_name,
            )

    def tick(self) -> None:
        """Advance completed captures and schedule due attempts."""
        now = self.clock()
        self._process_completed(now)
        self._schedule_due(now)

    def shutdown(self) -> None:
        """Cancel outstanding captures and release worker threads."""
        for event_id, event in list(self.events.items()):
            self._finish(event_id, event.camera)
        if self._owns_executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
