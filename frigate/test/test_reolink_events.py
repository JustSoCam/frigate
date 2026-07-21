from types import SimpleNamespace
from unittest import TestCase

from frigate.comms.event_metadata_updater import EventMetadataTypeEnum
from frigate.events.providers.reolink import ReolinkEventProvider


class FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, payload, topic="") -> None:
        self.messages.append((topic, payload))


class FakeHost:
    def __init__(self) -> None:
        self.states = {}

    def ai_detected(self, channel, label) -> bool:
        return self.states.get((channel, label), False)


def make_config(cameras):
    return SimpleNamespace(cameras=cameras)


def make_camera(enabled=True, **reolink):
    return SimpleNamespace(
        enabled=enabled,
        reolink=SimpleNamespace(
            enabled=True,
            port=9000,
            labels={"people": "person", "vehicle": "car", "dog_cat": "animal"},
            include_recording=True,
            score=1.0,
            disconnect_grace=15,
            **reolink,
        ),
    )


class TestReolinkEventProvider(TestCase):
    def test_groups_channels_using_the_same_endpoint(self):
        config = make_config(
            {
                "front": make_camera(
                    host="nvr", username="user", password="pass", channel=0
                ),
                "rear": make_camera(
                    host="nvr", username="user", password="pass", channel=1
                ),
            }
        )

        provider = ReolinkEventProvider(config)

        self.assertEqual(len(provider.endpoints), 1)
        self.assertEqual(
            {camera.camera for camera in provider.endpoints[0].cameras},
            {"front", "rear"},
        )

    def test_ai_transitions_create_once_and_end_matching_external_event(self):
        config = make_config(
            {
                "front": make_camera(
                    host="camera", username="user", password="pass", channel=0
                )
            }
        )
        provider = ReolinkEventProvider(config)
        publisher = FakePublisher()
        provider._publisher = publisher
        camera = provider.endpoints[0].cameras[0]
        host = FakeHost()

        host.states[(0, "people")] = True
        provider._reconcile_camera(host, camera)
        provider._reconcile_camera(host, camera)
        host.states[(0, "people")] = False
        provider._reconcile_camera(host, camera)

        self.assertEqual(len(publisher.messages), 2)
        create_topic, create_payload = publisher.messages[0]
        end_topic, end_payload = publisher.messages[1]
        self.assertEqual(
            create_topic, EventMetadataTypeEnum.manual_event_create.value
        )
        self.assertEqual(create_payload[1], "front")
        self.assertEqual(create_payload[2], "person")
        self.assertEqual(create_payload[6], "reolink_ai_people")
        self.assertIsNone(create_payload[7])
        self.assertEqual(create_payload[8], "reolink")
        self.assertEqual(end_topic, EventMetadataTypeEnum.manual_event_end.value)
        self.assertEqual(end_payload[0], create_payload[3])
        self.assertEqual(provider._active_events, {})
