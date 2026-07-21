import {
  FrigateConfig,
  PanelConfig,
  PanelTileConfig,
} from "@/types/frigateConfig";

export type NamedPanel = [name: string, config: PanelConfig];

export function legacyPanelTileId(
  cameras: string[],
  camera: string,
  index: number,
): string {
  const occurrence = cameras
    .slice(0, index + 1)
    .filter((candidate) => candidate === camera).length;
  return occurrence === 1 ? camera : `${camera}-${occurrence}`;
}

export function getConfiguredPanels(config: FrigateConfig): NamedPanel[] {
  if (config.panels !== null && config.panels !== undefined) {
    const panels = Object.entries(config.panels);
    return panels.sort((a, b) => a[1].order - b[1].order);
  }

  return Object.entries(config.camera_groups)
    .map<NamedPanel>(([name, group]) => [
      name,
      {
        icon: group.icon,
        order: group.order,
        tiles: group.cameras.map<PanelTileConfig>((camera, index) => ({
          id: legacyPanelTileId(group.cameras, camera, index),
          camera,
          crop: [0, 0, 1, 1],
        })),
      },
    ])
    .sort((a, b) => a[1].order - b[1].order);
}

export function getPanel(
  config: FrigateConfig,
  panelName: string | undefined,
): PanelConfig | undefined {
  if (!panelName || panelName === "default") {
    return undefined;
  }
  return getConfiguredPanels(config).find(([name]) => name === panelName)?.[1];
}
