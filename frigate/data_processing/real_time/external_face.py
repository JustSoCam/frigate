"""Deferred face enrichment for events created by camera-side detection."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any
from urllib.request import urlopen

import cv2
import numpy as np
from peewee import DoesNotExist

from frigate.models import Recordings
from frigate.util.image import get_image_from_recording

if TYPE_CHECKING:
    from frigate.config.config import FrigateConfig

    from .face import FaceRealTimeProcessor

logger = logging.getLogger(__name__)

GO2RTC_STREAMS_ENDPOINT = "http://127.0.0.1:1984/api/streams"
CAPTURE_ATTEMPTS = 6
RECORDING_SETTLE_DELAY = 12.0
RECORDING_RETRY_INTERVAL = 5.0
VIEWER_RETRY_INTERVAL = 3.0
MAX_RECORDING_WAIT = 90.0


def capture_recording_frame(
    config: FrigateConfig, camera: str, timestamp: float
) -> bytes | None:
    """Extract a full-resolution frame from an already stored recording."""
    try:
        recording = (
            Recordings.select(Recordings.path, Recordings.start_time)
            .where(
                (timestamp >= Recordings.start_time)
                & (timestamp <= Recordings.end_time)
                & (Recordings.camera == camera)
            )
            .order_by(Recordings.start_time.desc())
            .limit(1)
            .get()
        )
    except DoesNotExist:
        return None

    return get_image_from_recording(
        config.ffmpeg,
        recording.path,
        timestamp - recording.start_time,
        "mjpeg",
    )


def has_live_viewers() -> bool:
    """Return true when go2rtc has a consumer other than Frigate itself."""
    try:
        with urlopen(GO2RTC_STREAMS_ENDPOINT, timeout=1) as response:
            streams = json.load(response)
    except (OSError, ValueError):
        # Shed optional face work if viewer state cannot be established.
        return True

    for stream in streams.values():
        for consumer in stream.get("consumers", []):
            user_agent = str(consumer.get("user_agent") or "")
            if not user_agent.startswith("FFmpeg Frigate/"):
                return True
    return False


@dataclass
class ExternalFaceEvent:
    event_id: str
    camera: str
    start_time: float
    next_capture: float
    end_time: float | None = None
    capture_times: tuple[float, ...] = ()
    attempts: int = 0
    recording_wait_started: float | None = None


class ExternalFaceEnricher:
    """Run recording-backed face work only after alerts and viewers are gone."""

    def __init__(
        self,
        config: FrigateConfig,
        face_processor: FaceRealTimeProcessor,
        capture_frame: Callable[[str, float], bytes | None] | None = None,
        viewers_active: Callable[[], bool] = has_live_viewers,
        executor: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.face_processor = face_processor
        self.capture_frame = capture_frame or partial(capture_recording_frame, config)
        self.viewers_active = viewers_active
        self.clock = clock
        self.executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="external_face_capture",
        )
        self._owns_executor = executor is None
        self.events: dict[str, ExternalFaceEvent] = {}
        self.futures: dict[str, Future[bytes | None]] = {}
        self.viewer_blocked_until = 0.0

    def start(self, event_id: str, camera: str, start_time: float) -> None:
        """Remember an event without doing face work while its alert is active."""
        self._finish(event_id, camera)
        self.events[event_id] = ExternalFaceEvent(
            event_id,
            camera,
            start_time,
            math.inf,
        )
        logger.info("Queued deferred face enrichment for %s", camera)

    def end(self, event_id: str, camera: str, end_time: float) -> None:
        """Schedule recording-backed face work after an alert has ended."""
        event = self.events.get(event_id)
        if event is None:
            self.face_processor.expire_object(event_id, camera)
            return

        event.end_time = max(end_time, event.start_time)
        duration = event.end_time - event.start_time
        if duration <= 0:
            event.capture_times = (event.start_time,)
        else:
            step = duration / (CAPTURE_ATTEMPTS + 1)
            event.capture_times = tuple(
                event.start_time + step * index
                for index in range(1, CAPTURE_ATTEMPTS + 1)
            )
        now = self.clock()
        event.recording_wait_started = now
        event.next_capture = now + RECORDING_SETTLE_DELAY

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
                    "Recorded main-stream face capture failed for %s",
                    event.camera,
                )
                frame_bytes = None

            if not frame_bytes:
                event.next_capture = now + RECORDING_RETRY_INTERVAL
                continue

            event.attempts += 1
            recognized = False
            frame = cv2.imdecode(
                np.frombuffer(frame_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if frame is not None:
                logger.debug(
                    "Processing %dx%d recorded main-stream face frame for %s",
                    frame.shape[1],
                    frame.shape[0],
                    event.camera,
                )
                recognized = self.face_processor.process_external_frame(
                    event.event_id,
                    event.camera,
                    frame,
                )

            if recognized:
                logger.info(
                    "Matched face from recorded main stream for %s", event.camera
                )
                self._finish(event.event_id, event.camera)
            elif event.attempts >= len(event.capture_times):
                logger.info(
                    "No face match from recorded main stream for %s after %d attempts",
                    event.camera,
                    event.attempts,
                )
                self._finish(event.event_id, event.camera)
            else:
                event.next_capture = now

    def _schedule_due(self, now: float) -> None:
        due_events = [
            (event_id, event)
            for event_id, event in self.events.items()
            if event_id not in self.futures and event.next_capture <= now
        ]
        if not due_events:
            return

        for event_id, event in due_events:
            if (
                event.recording_wait_started is not None
                and now - event.recording_wait_started > MAX_RECORDING_WAIT
            ):
                logger.warning(
                    "Recorded main-stream frames did not become available for %s",
                    event.camera,
                )
                self._finish(event.event_id, event.camera)
                continue

            timestamp = event.capture_times[event.attempts]
            self.futures[event_id] = self.executor.submit(
                self.capture_frame,
                event.camera,
                timestamp,
            )

    def tick(self) -> None:
        """Advance completed captures and schedule due attempts."""
        now = self.clock()
        ready_future = any(future.done() for future in self.futures.values())
        due_event = any(
            event.end_time is not None
            and event_id not in self.futures
            and event.next_capture <= now
            for event_id, event in self.events.items()
        )
        if ready_future or due_event:
            # Active alerts and live viewers always outrank optional face work.
            if any(event.end_time is None for event in self.events.values()):
                return
            if now < self.viewer_blocked_until:
                return
            if self.viewers_active():
                self.viewer_blocked_until = now + VIEWER_RETRY_INTERVAL
                return

        self._process_completed(now)
        self._schedule_due(now)

    def shutdown(self) -> None:
        """Cancel outstanding captures and release the background worker."""
        for event_id, event in list(self.events.items()):
            self._finish(event_id, event.camera)
        if self._owns_executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
