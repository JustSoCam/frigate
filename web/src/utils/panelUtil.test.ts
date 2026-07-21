import { describe, expect, it } from "vitest";

import { FrigateConfig } from "@/types/frigateConfig";
import { getConfiguredPanels, getPanel } from "./panelUtil";

function configWith(
  values: Pick<FrigateConfig, "camera_groups" | "panels">,
): FrigateConfig {
  return values as FrigateConfig;
}

describe("panel utilities", () => {
  it("uses configured panels and preserves duplicate camera tiles", () => {
    const config = configWith({
      camera_groups: {
        outside: {
          cameras: ["driveway"],
          icon: "LuCamera",
          order: 1,
        },
      },
      panels: {
        detail: {
          icon: "LuScan",
          order: 1,
          tiles: [
            {
              id: "driveway-wide",
              camera: "driveway",
              crop: [0, 0, 1, 1],
            },
            {
              id: "driveway-gate",
              camera: "driveway",
              crop: [0.5, 0.25, 1, 0.75],
            },
          ],
        },
      },
    });

    const panel = getPanel(config, "detail");

    expect(panel?.tiles).toHaveLength(2);
    expect(panel?.tiles.map((tile) => tile.camera)).toEqual([
      "driveway",
      "driveway",
    ]);
    expect(panel?.tiles[1].crop).toEqual([0.5, 0.25, 1, 0.75]);
  });

  it("adapts legacy camera groups when no panels are configured", () => {
    const config = configWith({
      camera_groups: {
        outside: {
          cameras: ["driveway", "front_door"],
          icon: "LuCamera",
          order: 2,
        },
      },
      panels: null,
    });

    expect(getConfiguredPanels(config)).toEqual([
      [
        "outside",
        {
          icon: "LuCamera",
          order: 2,
          tiles: [
            {
              id: "driveway",
              camera: "driveway",
              crop: [0, 0, 1, 1],
            },
            {
              id: "front_door",
              camera: "front_door",
              crop: [0, 0, 1, 1],
            },
          ],
        },
      ],
    ]);
  });

  it("sorts panels by configured order", () => {
    const config = configWith({
      camera_groups: {},
      panels: {
        second: { icon: "LuCamera", order: 2, tiles: [] },
        first: { icon: "LuCamera", order: 1, tiles: [] },
      },
    });

    expect(getConfiguredPanels(config).map(([name]) => name)).toEqual([
      "first",
      "second",
    ]);
  });

  it("keeps legacy layout IDs while disambiguating legacy duplicates", () => {
    const config = configWith({
      camera_groups: {
        detail: {
          cameras: ["driveway", "driveway"],
          icon: "LuCamera",
          order: 1,
        },
      },
      panels: null,
    });

    expect(getPanel(config, "detail")?.tiles.map((tile) => tile.id)).toEqual([
      "driveway",
      "driveway-2",
    ]);
  });

  it("does not restore legacy groups after all panels are deleted", () => {
    const config = configWith({
      camera_groups: {
        outside: {
          cameras: ["driveway"],
          icon: "LuCamera",
          order: 1,
        },
      },
      panels: {},
    });

    expect(getConfiguredPanels(config)).toEqual([]);
  });
});
