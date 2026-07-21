---
id: live
title: Live View
---

import NavPath from "@site/src/components/NavPath";

**Live view** is Frigate's real-time dashboard and the page you land on by default. It shows all of your cameras at a glance, streams your most recent alerts across the top, and lets you open any camera in a full-resolution single-camera view with audio, two-way talk, PTZ, and on-demand recording controls.

This page describes how to _use_ the Live view. For how to _configure_ live streaming (go2rtc, stream selection, smart streaming, WebRTC, and audio), see the [Live View configuration](/configuration/live) docs.

## The dashboard at a glance

The default **All Cameras** dashboard shows every camera, with a filmstrip of recent **alerts** scrolling across the top. Clicking an alert opens it in [Review](/usage/review); each card also has a check button to mark it reviewed without leaving the dashboard. Only **alerts** appear in the filmstrip. To suppress a label or zone from showing there, configure it as a detection instead (see [Alerts and Detections](/configuration/review#alerts-and-detections)).

By default Frigate uses **smart streaming**: a camera's image updates roughly once per minute while nothing is happening, and switches to a full live stream the moment activity is detected. This conserves bandwidth and resources. You can change this for each camera on a panel (see [Streaming settings](#streaming-settings-and-the-right-click-menu) below), and the behavior is explained in detail under [Live view technologies](/configuration/live#live-view-technologies).

On mobile, a toggle in the header switches between a **grid** layout and a single-column **list** layout. On desktop a **fullscreen** button is available in the lower-right corner.

## Switching panels

The icon rail (top-left on desktop, a horizontal strip on mobile) switches between panels:

- The **home** icon is the **All Cameras** dashboard, which shows every camera enabled for the dashboard.
- Each **panel** you create appears as its own icon. A panel contains an ordered set of camera tiles with its own layout and streaming preferences.

Panels and camera groups are separate concepts. A **panel** is a screen you arrange and monitor. A **camera group** is a reusable named collection of cameras used by filters and other camera-selection controls. A panel can include any camera more than once, including independently framed detail views of a wide camera.

You can also view [Birdseye](/configuration/birdseye) on the dashboard, or open it directly at `http://<frigate_host>:5000/#birdseye`. Clicking a camera inside the Birdseye view jumps to that camera's live feed.

## Creating and editing panels

Admins can manage panels from the pencil icon next to the panel rail, which opens the **Panels** dialog. From there you can add a panel, or edit and delete existing ones. When creating a panel you choose:

- a **Name** (spaces are converted to underscores),
- one or more **tiles** for each camera (the plus and minus controls change the number of instances),
- the **framing** for each tile (zoom and horizontal/vertical position),
- an **icon** used for the panel's button in the rail.

Adding another tile does not create another connection to the physical camera. Frigate's local stream is reused, and framing is applied as a display transform without transcoding or additional latency. Each tile still consumes browser decoding and local network resources while it is actively streaming.

Existing camera groups automatically appear as equivalent panels until the first panel is saved. This preserves existing configurations and per-device layouts while allowing camera groups to remain available for filtering.

Deleting a panel also clears any custom layout you saved for it.

## Rearranging a panel layout

On desktop and tablet, each panel has its own freely-arrangeable grid. Enter **Edit Layout** mode from the layout button in the lower-right corner: camera tiles gain a drag handle and corner resize handles. Drag a tile to reposition it and drag a corner to resize it (the aspect ratio is preserved). Exit edit mode to save. The layout is stored in your browser per device, so each device can have its own arrangement.

The default **All Cameras** dashboard is not manually arrangeable. It automatically sizes tiles based on each camera's aspect ratio (wide cameras span two columns, tall cameras span two rows).

## Reading the tile indicators

Each camera tile surfaces its current state with a few overlays:

- A **pulsing red dot** in the corner means **motion is currently detected** on that camera.
- A **red outline** around the tile means an **active tracked object** is on that camera.
- A small **label chip** lists the object types currently detected (for example, _Person_, _Car_).
- A **camera-name label** appears when you have enabled always-on camera names, or when a camera is offline or disabled.
- A **Stream Offline** or **Camera is off** placeholder appears when no frames are being received or the camera has been turned off.

You can optionally overlay live streaming statistics (stream type, bandwidth, latency, and frame counts) on a tile to diagnose playback issues.

## Streaming settings and the right-click menu

Right-clicking (or long-pressing) a camera tile opens a context menu with quick controls: an **audio volume** control for streams that support audio, **Mute / Unmute all cameras**, **show or hide streaming statistics**, the **debug view**, **notification** options, and, for admins, turning the camera on or off. If the audio control doesn't appear, see [Audio Support](/configuration/live#audio-support). Audio requires go2rtc configured with a compatible codec.

A **Low-bandwidth mode** notice may also appear in the context menu with a **Reset** option when Frigate has fallen back to the lower-quality jsmpeg stream. See the [Live view FAQ](/configuration/live#live-view-faq) for why this happens.

For non-default panels, the context menu also exposes **Streaming Settings** for that camera, which let you choose:

- the **stream** to display (the dropdown lists the streams you configured under [`live -> streams`](/configuration/live#setting-streams-for-live-ui), and indicates whether audio is available),
- the **streaming method**: **No Streaming**, **Smart Streaming** (recommended), or **Continuous Streaming** (higher bandwidth), and
- **compatibility mode**, for devices that have trouble rendering the default player.

These settings are saved per group and per device in your browser, not in your config file.

## The single-camera view

Clicking a camera tile opens its full-resolution single-camera view. The top bar provides:

- **Back** (also the `Esc` key) to return to the dashboard,
- **History** to jump to the [recordings](/usage/history) for this camera, starting about 30 seconds in the past,
- **Fullscreen** and **Picture-in-Picture** (if supported by your browser),
- **Two-way talk** (the microphone button, which requires a supported camera and WebRTC; keyboard shortcut `t`), and
- **Camera audio muting** (the speaker button; keyboard shortcut `m`).

You can pinch or scroll to zoom into the feed. A **settings** gear provides a **stream** selector (with audio and two-way-talk availability indicators), **Play in background**, **Show stats**, and a **Debug view** that overlays Frigate's detection regions and bounding boxes.

:::tip

Two-way talk and camera audio have specific codec and port requirements. See [Audio Support](/configuration/live#audio-support) and [WebRTC](/configuration/live#webrtc-extra-configuration) for setup details.

:::

## Camera controls

Admins get a row of toggles in the single-camera view (a settings drawer on mobile) to turn camera features on and off in real time:

- **Camera** on/off,
- **Object detection**,
- **Recording** (only available when recording is enabled in the camera's config),
- **Snapshots**,
- **Audio detection**,
- **Live audio transcription** (when audio detection is enabled), and
- **Autotracking** (for [autotracking-capable PTZ cameras](/configuration/autotracking)).

These toggles change runtime behavior immediately. Whether a change persists across a restart depends on the feature. See the relevant configuration page.

## On-demand recording and snapshots

The single-camera view can capture footage on demand:

- **Start on-demand recording** begins a manual recording based on the camera's recording retention settings (the button pulses while active). If recording is disabled for the camera, only a snapshot is saved. Use **End on-demand recording** to stop.
- **Download instant snapshot** saves a still image of the current frame.

See [Recording](/configuration/record) and [Snapshots](/configuration/snapshots) for how retention is configured, and [Exports](/usage/exports) for keeping a clip permanently.

## PTZ controls

For ONVIF cameras that support it, a control panel provides pan/tilt arrows, **zoom**, **focus**, and saved **presets**. You can also enable a **click-to-move / drag-to-zoom** overlay: click a point in the frame to center the camera there, or drag a box to pan and zoom to that area (dragging top-left to bottom-right zooms in, the reverse zooms out).

For continuous, automatic tracking of a moving object, see [Autotracking](/configuration/autotracking).
