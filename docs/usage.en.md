# Usage Guide

[中文](usage.md) · [Back to README](../README.en.md)

For everyday operation, the app includes contextual controls. This page collects the detailed steps. [3D interaction controls remain in the README](../README.en.md#3d-interaction-controls).

## Generate 3D Models

1. **Upload Image** - Click "Generate / Import Model" or drag images to the sidebar
2. **Wait for Processing** - Watch the queue stages (if installation did not finish the download, first inference downloads the approximately 2.62 GiB model)
3. **Preview Model** - Click gallery items to view 3D

## Manage the Model Asset Library

1. **Browse assets** - Generated results and imported models appear in one asset library. The main grid uses cursor-based incremental scroll loading, not a paginator or per-page selector.
2. **Open and inspect** - Click the non-button area of a model card to open the viewer. On desktop, the hover details button opens the right details panel; on mobile, tapping a card opens the details card.
3. **Import models** - Use "Import Model" or drop `.ply/.spz/.splat/.rad` files. Dropping one model opens a temporary preview first; dropping multiple models imports them into the asset library.
4. **Format preference** - Settings > Default Model Format controls whether SPZ or PLY is preferred for recent models, asset opening, and downloads. If the preferred file is unavailable, Sharp GUI falls back to an available model file.
5. **Details metadata** - File name, format, source, timestamps, and size come from the index and filesystem. PLY/SPLAT can expose some point count or property data; SPZ/RAD bounding boxes, coordinate systems, LoD, and similar advanced fields only appear when the source file or sidecar metadata provides them, so unknown fields are not fabricated.
6. **View source media** - The details-panel thumbnail opens the linked source image or video when one exists. Without a linked source, it only acts as the model cover.

External models default to the video model orientation and bounds-centered framing branch. Original ml-sharp PLY files with the complete camera / image element schema use the single-image preview. SPZ, SPLAT, and unmarked PLY files do not establish provenance; these assets remain classified as Imported. Explicit calibration and saved cameras take precedence. Importing copies the file without rewriting coordinates. See the [external preview details (Chinese)](imported-model-preview.md).

For an editable temporary preview, choose **Add & Edit** to save it to the asset library and enter the editor, or use **Add to Library** to import only. Original multi-element ml-sharp PLY and RAD remain unsupported for editing.

### Reconstruction Information

New image and video models show their measured reconstruction time in asset details. Timing starts when processing begins and ends after model export and compact-file postprocessing; queue time is excluded. Video summaries include the engine version, preset, source resolution, registered frames, training iterations and image long-edge cap. Expand stage timings to inspect extraction, camera reconstruction, training and export. Image summaries include the device, source dimensions, inference and postprocessing times.

Records persist in the model's `.meta.json` sidecar. Historical assets without measurements show “Not recorded”; file dates are never used to estimate duration. Edited copies retain and label the original reconstruction record, which is not editing time. PLY/SPZ remain standard model files; keep the sidecar when moving application-level records between projects.

Existing models require reconstruction to benefit from the new training engine. See the [deployment guide](deployment.en.md) for engine installation and portable-runtime compatibility.

## Edit Models

1. **Open the editor** — Use Edit Model on an asset card or in its details, or open the model and use the bottom toolbar.
2. **Select and clean up** — Select splats with rectangle, sphere, or box tools, then delete the selection or keep only it. Drag numeric values or selection boundaries, with fine adjustment and undo / redo.
3. **Calibrate coordinates** — Set Origin moves the proposed zero point while the model stays still; Rotate levels the model around that point. Saving writes this calibration into the model file. The initial viewing camera can be set separately.
4. **Save the result** — Save as New Model is the default; the adjacent menu also offers Overwrite Original Model. The list refreshes after saving, and source image / video links are retained.

Editing is available to the local owner for standard Gaussian PLY, supported SPZ versions, and SPLAT. RAD, ordinary point clouds, and original ml-sharp PLY files with extra camera elements are currently unsupported; their entry is disabled or hidden. Deletion removes whole Gaussians. See the [editing guide and limits (Chinese)](model-editor.md).

## Export Animation

1. **Open the tool** — Open a model and choose Export animation in the bottom toolbar.
2. **Record shots** — Adjust the viewing angle, position, and zoom, then record the current view. Record at least two shots and set transition durations. Shots can be replaced, reordered, or deleted.
3. **Preview motion** — Choose Continuous glide, Standard ease, Sine ease, Soft landing, or Linear motion, then play or scrub the timeline. Path overview independently shows numbered keyframes, the camera route, and viewing frustums; return to Shot preview to record more views.
4. **Export video** — Choose landscape / portrait, 1080p / 4K, and 24 / 30 / 60 fps. Export, then download the silent WebM or MP4. Path helpers stay out of the video.

Use **Play preview** below the canvas to watch the motion. **Restore initial model view** resets only the observation camera and does not delete or replace keyframes.

Export requires browser WebCodecs support and HTTPS or a localhost address; available encoding settings depend on the device. Save shots as JSON before refreshing or switching models, and load them to resume later. See the [animation export guide, curves, and limits (Chinese)](camera-animation.md).

## Browse Local Media Albums

1. **Switch to Gallery** - Use the sidebar `Models / Gallery` entry to open the local media gallery
2. **Add Folder** - From localhost, add Windows / Linux / macOS paths; each folder is shown as an album
3. **Browse Media** - Photos use cached thumbnails and open originals on demand; videos can be previewed, scrubbed, viewed fullscreen, and downloaded
4. **Upload to Album** - Pick or drag photos into the current album; the album refreshes automatically
5. **Convert to 3D** - Convert photos from cards or the preview layer, or multi-select and queue a batch into the existing workflow
6. **Open existing models** — Blue 3D badges identify media with models. View 3D in the preview opens the result; multiple results offer version selection, a default model, and another generation action.
7. **Browse model sources** — The pinned Model Sources album gathers photos / videos linked to generated models. Each source appears once, with edited copies and repeat reconstructions grouped together. Unavailable album paths remain listed with a message, while existing models can still be viewed. See the [linking guide (Chinese)](model-source-gallery.md).

## Generate 3D Models from Video

Check dependencies in Settings > Video Reconstruction. **Brush** trains the model with COLMAP camera alignment. See [Video Reconstruction Manual Environment Setup](deployment.en.md#video-reconstruction-manual-environment-setup).

1. **Select a video** - Choose one album video or drop one video into the model view, model list or Generate New entry.
2. **Choose quality** - Brush custom settings expose frame count, iterations, an actual long-edge pixel cap and matching method.
3. **Reconstruct** - After extraction and alignment, training requires at least 8 registered frames and a 50% registration rate. Poor alignment triggers one retry with denser sampling or broader matching; if it still fails, recapture or split the clip. Before Brush training, images and camera intrinsics are undistorted together, and camera poses and sparse points are rotated to share a consistent up direction.
4. **View the result** - Open the gallery model, replay the source, or download PLY/SPZ. New SPZ exports retain higher-order spherical harmonics; old SH0 files require conversion from their original PLY to restore those coefficients.

Brush presets:

| Preset | Iterations | Image long-edge cap |
| --- | ---: | --- |
| Preview | 8,000 | 1600 pixels |
| High | 15,000 | 1920 pixels |
| Extreme | 30,000 | Adjusted to VRAM budget |
| Custom | 1,000–80,000 | 640–3840 pixels |

Preview, High and Extreme initially sample about 6 / 8 / 12 frames per second, with 1200 / 1600 / 3200 pixel camera registration caps and 4096 / 8192 / 16384 feature budgets. These correspond to OOOSplat's Fast, Balanced and High recipes. High retains a 1920 pixel training cap; Extreme retains 3840 pixels with a 12 GB budget. Denser candidate pools use about 9 / 12 / 15 frames per second and preserve the initial list. Unknown source frame counts fall back to time sampling. See the [quality validation record](video-reconstruction-quality.md) for the same-video comparison and its limits.

- **Long videos**: start with Custom at 600 frames / 15k / 1920 pixels / sequential matching. More frames increase geometry and training cost. Exhaustive matching is limited to 450 frames.
- **Modes**: Auto and Environment keep the full reconstruction. Only Object crops around the subject, which may remove surrounding geometry; automatic foreground masks are not provided.
- **VRAM**: choose the actual GPU capacity. The target laptop has 12 GB, so a 16 GB budget is inappropriate.
- **Diagnostics**: a compact report remains in the model sidecar. Keep intermediate files to inspect frames, poses and training files, including the original PLY before object cropping.
- **Initial view**: new Brush models preserve a registered camera viewpoint, keeping the subject visible when distant splats pull the bounding-box center away.
- **Validation scope**: synthetic workflow tests and a complete local reconstruction of a nonsensitive video have passed, including PLY renders and SPZ viewer validation. Quality depends on the footage. Runtime depends on camera alignment and scene size, and extra iterations cannot recover missing views.
- **Scope**: one video per static 3DGS task. Joint multi-image reconstruction has not been integrated.

## Export & Share

For a generated model, click **Share** in the viewer or **Export** in its asset library details to generate a standalone HTML file:

- 📦 Complete 3D viewer included (Three.js + Spark 2.0)
- 🌐 No server needed; open offline in a WebGL2-capable browser
- 📉 Embeds compact SPZ by default; the legacy PLY/Splat export path remains available for compatibility
- 🎥 Preserves orientation and the saved view, with full-model framing, auto-orbit, backgrounds, fullscreen, and mobile controls
- 🔒 Includes disclaimer about content responsibility

Standalone HTML sharing currently supports generated models; directly imported or temporarily opened assets are not supported. The HTML contains the model data and cannot be recalled through the original app once sent. See the [standalone sharing guide (Chinese)](standalone-sharing.md) for scope and offline usage.

## 🔧 Advanced Features

- **🔒 HTTPS Support** - Auto-generated self-signed certificates for safer LAN access (browsers require secure context for sensor APIs)
- **📦 File Optimization** - Auto-generates compact SPZ models, usually **5-10x smaller** than PLY while preserving the original PLY
- **🧹 Auto Cleanup** - Completed tasks auto-removed from memory after 1 hour to prevent leaks
- **⚙️ Configurable Paths** - Custom workspace folder, supports Windows / Linux / macOS
- **🖥️ Fullscreen Mode** - Immersive 3D preview
- **🥽 WebXR** - VR preview + AR Passthrough on Quest 3/Pro and similar headsets
- **🎯 Click-to-Focus** - WASM-accelerated raycasting + GPU focus ring animation
- **🌐 i18n** - Chinese/English bilingual UI, auto-detects browser language, manual toggle
