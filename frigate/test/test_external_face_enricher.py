from concurrent.futures import Future
from unittest import TestCase

import cv2
import numpy as np

from frigate.data_processing.real_time.external_face import (
    CAPTURE_INTERVAL,
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

    def test_retries_main_stream_until_face_is_recognized(self):
        processor = FakeFaceProcessor([False, True])
        streams = []
        enricher = ExternalFaceEnricher(
            processor,
            capture_frame=lambda stream: streams.append(stream) or self.frame,
            executor=ImmediateExecutor(),
            clock=lambda: self.now,
        )

        enricher.start("event-1", "front", "front-main")
        self.now += 1
        enricher.tick()
        enricher.tick()
        self.now += CAPTURE_INTERVAL
        enricher.tick()
        enricher.tick()

        self.assertEqual(streams, ["front-main", "front-main"])
        self.assertEqual(len(processor.processed), 2)
        self.assertNotIn("event-1", enricher.events)
        self.assertIn(("event-1", "front"), processor.expired)

    def test_event_end_keeps_one_inflight_capture_but_stops_retries(self):
        processor = FakeFaceProcessor([False])
        enricher = ExternalFaceEnricher(
            processor,
            capture_frame=lambda _stream: self.frame,
            executor=ImmediateExecutor(),
            clock=lambda: self.now,
        )

        enricher.start("event-1", "front", "front-main")
        enricher.end("event-1", "front")
        enricher.tick()
        self.now += 10
        enricher.tick()

        self.assertEqual(len(processor.processed), 1)
        self.assertNotIn("event-1", enricher.events)
