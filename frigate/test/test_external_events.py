from types import SimpleNamespace
from unittest import TestCase

from frigate.comms.detections_updater import DetectionTypeEnum
from frigate.events.types import EventStateEnum, EventTypeEnum
from frigate.track.object_processing import (
    ManualEventState,
    TrackedObjectProcessor,
)


class FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, payload, topic="") -> None:
        self.messages.append((topic, payload))


class FakeCameraState:
    def save_manual_event_image(self, *_args) -> None:
        pass


class TestExternalEvents(TestCase):
    def setUp(self) -> None:
        self.processor = TrackedObjectProcessor.__new__(TrackedObjectProcessor)
        self.processor.camera_states = {"front": FakeCameraState()}
        self.processor.config = SimpleNamespace(
            cameras={
                "front": SimpleNamespace(
                    record=SimpleNamespace(enabled=True, event_pre_capture=5)
                )
            }
        )
        self.processor.event_sender = FakePublisher()
        self.processor.detection_publisher = FakePublisher()
        self.processor.ongoing_manual_events = {}

    def test_reolink_event_uses_external_detection_topic_for_start_and_end(self):
        self.processor.create_manual_event(
            (
                100.0,
                "front",
                "person",
                "event-id",
                True,
                1.0,
                "reolink_ai_people",
                None,
                "reolink",
                {},
                None,
            )
        )

        _, event_update = self.processor.event_sender.messages[0]
        self.assertEqual(event_update[0], EventTypeEnum.api)
        self.assertEqual(event_update[1], EventStateEnum.start)
        self.assertEqual(event_update[4]["type"], "reolink")
        self.assertEqual(event_update[4]["start_time"], 95.0)

        topic, detection = self.processor.detection_publisher.messages[0]
        self.assertEqual(topic, DetectionTypeEnum.external.value)
        self.assertEqual(detection[2]["state"], ManualEventState.start)

        self.processor.end_manual_event(("event-id", 110.0))

        topic, detection = self.processor.detection_publisher.messages[1]
        self.assertEqual(topic, DetectionTypeEnum.external.value)
        self.assertEqual(detection[2]["state"], ManualEventState.end)
