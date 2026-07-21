"""Native Reolink TCP-push AI event provider."""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from frigate.comms.event_metadata_updater import (
    EventMetadataPublisher,
    EventMetadataTypeEnum,
)

if TYPE_CHECKING:
    from frigate.config.config import FrigateConfig

logger = logging.getLogger(__name__)

REOLINK_CLEANUP_TIMEOUT = 5.0


@dataclass(frozen=True)
class ReolinkCamera:
    camera: str
    channel: int
    labels: dict[str, str]
    include_recording: bool
    score: float
    disconnect_grace: int


@dataclass(frozen=True)
class ReolinkEndpoint:
    host: str
    port: int
    username: str
    password: str
    cameras: tuple[ReolinkCamera, ...]


class ReolinkEventProvider(threading.Thread):
    """Translate camera-side Reolink AI transitions into Frigate events."""

    def __init__(self, config: FrigateConfig) -> None:
        super().__init__(name="reolink_event_provider")
        self.endpoints = self._build_endpoints(config)
        self._active_events: dict[tuple[str, str], str] = {}
        self._stop_requested = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_stop: asyncio.Event | None = None
        self._publisher: EventMetadataPublisher | None = None

    @staticmethod
    def _build_endpoints(config: FrigateConfig) -> tuple[ReolinkEndpoint, ...]:
        grouped: dict[tuple[str, int, str, str], list[ReolinkCamera]] = defaultdict(
            list
        )
        for camera_name, camera_config in config.cameras.items():
            reolink = camera_config.reolink
            if not camera_config.enabled or not reolink.enabled:
                continue
            grouped[
                (reolink.host, reolink.port, reolink.username, reolink.password)
            ].append(
                ReolinkCamera(
                    camera=camera_name,
                    channel=reolink.channel,
                    labels=dict(reolink.labels),
                    include_recording=reolink.include_recording,
                    score=reolink.score,
                    disconnect_grace=reolink.disconnect_grace,
                )
            )

        return tuple(
            ReolinkEndpoint(host, port, username, password, tuple(cameras))
            for (host, port, username, password), cameras in grouped.items()
        )

    @property
    def enabled(self) -> bool:
        return bool(self.endpoints)

    def stop(self) -> None:
        self._stop_requested.set()
        if self._loop is not None and self._async_stop is not None:
            self._loop.call_soon_threadsafe(self._async_stop.set)

    def run(self) -> None:
        if not self.enabled:
            return
        try:
            asyncio.run(self._run())
        except Exception:
            logger.exception("Reolink event provider stopped unexpectedly")

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()
        self._publisher = EventMetadataPublisher()
        tasks = [
            asyncio.create_task(self._run_endpoint(endpoint))
            for endpoint in self.endpoints
        ]
        logger.info(
            "Starting native Reolink AI events for %d camera(s) across %d endpoint(s)",
            sum(len(endpoint.cameras) for endpoint in self.endpoints),
            len(self.endpoints),
        )

        if self._stop_requested.is_set():
            self._async_stop.set()
        await self._async_stop.wait()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._end_all_events()
        self._publisher.stop()
        self._publisher = None

    async def _run_endpoint(self, endpoint: ReolinkEndpoint) -> None:
        # Import here so installations that do not enable this provider do not
        # require the optional camera protocol dependency at module import time.
        from reolink_aio.api import Host

        delay = 1.0
        while not self._stop_requested.is_set():
            host: Any | None = None
            callback_ids: list[str] = []
            try:
                host = Host(
                    endpoint.host,
                    endpoint.username,
                    endpoint.password,
                    bc_port=endpoint.port,
                    bc_only=True,
                )
                await host.get_host_data()
                for camera in endpoint.cameras:
                    callback_id = f"frigate-{camera.camera}"
                    callback_ids.append(callback_id)
                    host.baichuan.register_callback(
                        callback_id,
                        partial(self._reconcile_camera, host, camera),
                        cmd_id=33,
                        channel=camera.channel,
                    )

                await host.baichuan.subscribe_events()
                for camera in endpoint.cameras:
                    self._reconcile_camera(host, camera)
                logger.info(
                    "Connected to Reolink AI events at %s:%d",
                    endpoint.host,
                    endpoint.port,
                )
                delay = 1.0
                await self._monitor_connection(host, endpoint)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error(
                    "Reolink AI connection to %s:%d failed: %s",
                    endpoint.host,
                    endpoint.port,
                    error,
                )
            finally:
                if host is not None:
                    await self._cleanup_host(host, endpoint, callback_ids)

            if self._stop_requested.is_set():
                break
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
            delay = min(delay * 2, 60)

    async def _cleanup_host(
        self, host: Any, endpoint: ReolinkEndpoint, callback_ids: list[str]
    ) -> None:
        """Bound teardown so a broken session cannot prevent reconnection."""
        for callback_id in callback_ids:
            host.baichuan.unregister_callback(callback_id)

        await self._bounded_cleanup(
            host.baichuan.unsubscribe_events(),
            endpoint,
            "unsubscribe",
        )
        await self._bounded_cleanup(host.logout(), endpoint, "close")

    async def _bounded_cleanup(
        self, cleanup: Awaitable[Any], endpoint: ReolinkEndpoint, operation: str
    ) -> None:
        try:
            await asyncio.wait_for(cleanup, timeout=REOLINK_CLEANUP_TIMEOUT)
        except TimeoutError:
            logger.warning(
                "Timed out waiting to %s Reolink endpoint %s:%d",
                operation,
                endpoint.host,
                endpoint.port,
            )
        except Exception:
            logger.debug(
                "Failed to %s Reolink endpoint %s:%d",
                operation,
                endpoint.host,
                endpoint.port,
                exc_info=True,
            )

    async def _monitor_connection(self, host: Any, endpoint: ReolinkEndpoint) -> None:
        disconnected_at: float | None = None
        while not self._stop_requested.is_set():
            await asyncio.sleep(1)
            if host.session_active and host.baichuan.events_active:
                disconnected_at = None
                continue

            if disconnected_at is None:
                disconnected_at = time.monotonic()

            elapsed = time.monotonic() - disconnected_at
            for camera in endpoint.cameras:
                if elapsed >= camera.disconnect_grace:
                    self._end_camera_events(camera.camera)

            # Force a clean outer-loop reconnect if the library has not restored
            # the push session. This also bounds stale subscriptions.
            if elapsed >= max(
                30, max(camera.disconnect_grace for camera in endpoint.cameras)
            ):
                raise ConnectionError("Reolink push session did not recover")

    def _reconcile_camera(self, host: Any, camera: ReolinkCamera) -> None:
        for reolink_label, frigate_label in camera.labels.items():
            key = (camera.camera, reolink_label)
            detected = bool(host.ai_detected(camera.channel, reolink_label))
            if detected and key not in self._active_events:
                self._start_event(camera, reolink_label, frigate_label)
            elif not detected and key in self._active_events:
                self._end_event(key)

    def _start_event(
        self, camera: ReolinkCamera, reolink_label: str, frigate_label: str
    ) -> None:
        if self._publisher is None:
            return
        now = time.time()
        event_id = f"{now}-reolink-{uuid.uuid4().hex[:8]}"
        self._active_events[(camera.camera, reolink_label)] = event_id
        self._publisher.publish(
            (
                now,
                camera.camera,
                frigate_label,
                event_id,
                camera.include_recording,
                camera.score,
                f"reolink_ai_{reolink_label}",
                None,
                "reolink",
                {},
                None,
            ),
            EventMetadataTypeEnum.manual_event_create.value,
        )
        logger.info("Reolink AI event started for %s: %s", camera.camera, frigate_label)

    def _end_event(self, key: tuple[str, str]) -> None:
        event_id = self._active_events.pop(key, None)
        if event_id is None or self._publisher is None:
            return
        self._publisher.publish(
            (event_id, time.time()),
            EventMetadataTypeEnum.manual_event_end.value,
        )
        logger.info("Reolink AI event ended for %s: %s", key[0], key[1])

    def _end_camera_events(self, camera: str) -> None:
        for key in tuple(self._active_events):
            if key[0] == camera:
                self._end_event(key)

    def _end_all_events(self) -> None:
        for key in tuple(self._active_events):
            self._end_event(key)
