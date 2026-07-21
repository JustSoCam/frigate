from pydantic import Field, model_validator

from ..base import FrigateBaseModel
from ..env import EnvString

__all__ = ["ReolinkConfig"]


class ReolinkConfig(FrigateBaseModel):
    """Reolink camera-side AI event configuration."""

    enabled: bool = Field(
        default=False,
        title="Enable Reolink AI events",
        description="Use native Reolink TCP push events as external detections.",
    )
    host: EnvString = Field(
        default="",
        title="Reolink host",
        description="Hostname or IP address used by the native Reolink protocol.",
    )
    port: int = Field(default=9000, ge=1, le=65535, title="Reolink TCP port")
    username: EnvString = Field(default="", title="Reolink username")
    password: EnvString = Field(default="", title="Reolink password")
    channel: int = Field(default=0, ge=0, title="Reolink channel")
    labels: dict[str, str] = Field(
        default_factory=lambda: {
            "people": "person",
            "vehicle": "car",
            "dog_cat": "animal",
        },
        title="Reolink AI label mapping",
        description="Map Reolink AI object types to Frigate labels.",
    )
    include_recording: bool = Field(
        default=True,
        title="Include recording",
        description="Associate recording footage with Reolink AI events.",
    )
    score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        title="External event score",
    )
    disconnect_grace: int = Field(
        default=15,
        ge=0,
        le=300,
        title="Disconnect grace period",
        description="Seconds to wait before ending active events after a connection loss.",
    )

    @model_validator(mode="after")
    def validate_enabled_connection(self):
        if self.enabled and (not self.host or not self.username or not self.password):
            raise ValueError(
                "Reolink host, username, and password are required when enabled"
            )
        if self.enabled and not self.labels:
            raise ValueError("At least one Reolink AI label mapping is required")
        if any(not source or not target for source, target in self.labels.items()):
            raise ValueError("Reolink AI label mappings must not be empty")
        return self
