from pydantic import Field, field_validator, model_validator

from .base import FrigateBaseModel

__all__ = ["PanelConfig", "PanelTileConfig"]


class PanelTileConfig(FrigateBaseModel):
    id: str = Field(
        title="Tile ID",
        description="Stable identifier for this tile within its panel.",
    )
    camera: str = Field(
        title="Camera",
        description="Camera or special live source displayed by this tile.",
    )
    crop: tuple[float, float, float, float] = Field(
        default=(0.0, 0.0, 1.0, 1.0),
        title="Crop",
        description=(
            "Normalized crop rectangle as left, top, right, and bottom coordinates."
        ),
    )

    @field_validator("crop")
    @classmethod
    def validate_crop(
        cls, crop: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        left, top, right, bottom = crop
        if any(value < 0 or value > 1 for value in crop):
            raise ValueError("Crop coordinates must be between 0 and 1")
        if left >= right or top >= bottom:
            raise ValueError("Crop must have a positive width and height")
        return crop


class PanelConfig(FrigateBaseModel):
    tiles: list[PanelTileConfig] = Field(
        default_factory=list,
        title="Panel tiles",
        description="Ordered camera tiles displayed on this panel.",
    )
    icon: str = Field(
        default="generic",
        title="Panel icon",
        description="Icon used to represent the panel in the Live view.",
    )
    order: int = Field(
        default=0,
        title="Sort order",
        description="Numeric order used to sort panels; larger numbers appear later.",
    )

    @model_validator(mode="after")
    def validate_unique_tile_ids(self):
        tile_ids = [tile.id for tile in self.tiles]
        if len(tile_ids) != len(set(tile_ids)):
            raise ValueError("Panel tile IDs must be unique")
        return self
