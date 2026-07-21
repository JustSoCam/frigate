import unittest

from pydantic import ValidationError

from frigate.config.panel import PanelConfig, PanelTileConfig


class TestPanelConfig(unittest.TestCase):
    def test_allows_duplicate_camera_sources_with_unique_tile_ids(self):
        panel = PanelConfig(
            tiles=[
                PanelTileConfig(id="driveway-wide", camera="driveway"),
                PanelTileConfig(
                    id="driveway-gate",
                    camera="driveway",
                    crop=(0.5, 0.25, 1.0, 0.75),
                ),
            ]
        )

        self.assertEqual(2, len(panel.tiles))
        self.assertEqual(panel.tiles[0].camera, panel.tiles[1].camera)

    def test_rejects_duplicate_tile_ids(self):
        with self.assertRaises(ValidationError):
            PanelConfig(
                tiles=[
                    PanelTileConfig(id="driveway", camera="driveway"),
                    PanelTileConfig(id="driveway", camera="front_door"),
                ]
            )

    def test_rejects_invalid_crop_coordinates(self):
        invalid_crops = [
            (-0.1, 0.0, 1.0, 1.0),
            (0.0, 0.0, 1.1, 1.0),
            (0.5, 0.0, 0.5, 1.0),
            (0.0, 0.75, 1.0, 0.25),
        ]

        for crop in invalid_crops:
            with self.subTest(crop=crop), self.assertRaises(ValidationError):
                PanelTileConfig(id="driveway", camera="driveway", crop=crop)


if __name__ == "__main__":
    unittest.main()
