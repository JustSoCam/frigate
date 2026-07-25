from concurrent.futures import Future
from types import SimpleNamespace
from unittest import TestCase

import cv2
import numpy as np

from frigate.data_processing.real_time.external_face import (
    RECORDING_SETTLE_DELAY,
    ExternalFaceEnricher,
)


class ImmediateExecutor:
    def submit(self, fn, *args):
        future = Future()
        future.set_result(fn(*args))
        return future


class FakeFaceProcessor:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.processed = []
        self.expired = []

    def process_external_frame(self, event_id, camera, frame):
        self.processed.append((event_id, camera, frame.shape))
        return next(self.outcomes)

    def expire_object(self, event_id, camera):
        self.expired.append((event_id, camera))


class TestExternalFaceEnricher(TestCase):
    def setUp(self):
        self.now = 100.0
        image = np.zeros((2160, 3840, 3), dtype=np.uint8)
        success, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(success)
        self.frame = encoded.tobytes()

    def test_waits_for_event_end_then_retries_recordings_until_recognized(self):
        processor = FakeFaceProcessor([False, True])
        captures = []
        enricher = ExternalFaceEnricher(
            SimpleNamespace(),
            processor,
            capture_frame=lambda camera, timestamp: captures.append((camera, timestamp))
            or self.frame,
            viewers_active=lambda: False,
            executor=ImmediateExecutor(),
            clock=lambda: self.now,
        )

        enricher.start("event-1", "front", 10.0)
        self.now += 20
        enricher.tick()
        self.assertEqual(captures, [])

        enricher.end("event-1", "front", 24.0)
        self.now += RECORDING_SETTLE_DELAY
        enricher.tick()
        enricher.tick()
        enricher.tick()
        enricher.tick()

        self.assertEqual(len(captures), 2)
        self.assertEqual(captures[0][0], "front")
        self.assertEqual(len(processor.processed), 2)
        self.assertNotIn("event-1", enricher.events)
        self.assertIn(("event-1", "front"), processor.expired)

    def test_live_viewer_pauses_face_work_after_event_end(self):
        processor = FakeFaceProcessor([False])
        viewing = True
        captures = []
        enricher = ExternalFaceEnricher(
            SimpleNamespace(),
            processor,
            capture_frame=lambda camera, timestamp: captures.append((camera, timestamp))
            or self.frame,
            viewers_active=lambda: viewing,
            executor=ImmediateExecutor(),
            clock=lambda: self.now,
        )

        enricher.start("event-1", "front", 10.0)
        enricher.end("event-1", "front", 20.0)
        self.now += RECORDING_SETTLE_DELAY
        enricher.tick()
        self.assertEqual(captures, [])

        viewing = False
        self.now += 3
        enricher.tick()
        enricher.tick()

        self.assertEqual(len(processor.processed), 1)
        self.assertGreaterEqual(len(captures), 1)
