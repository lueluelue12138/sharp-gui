# Sharp GUI

<p align="right">
  <a href="README.md">🇨🇳 中文</a> | <a href="README.en.md">🇺🇸 English</a>
</p>

<div align="center">

**A Beautiful 3D Gaussian Splatting GUI**

<img src="assets/logo.png" alt="Sharp GUI Logo" width="200" />

<br>

**💡 Background**

Homepage: https://lueluelue12138.github.io/sharp-gui/

The "Spatial Photos" feature in iOS 26 offers an amazing immersive experience, but is currently limited to the Apple ecosystem.

As a Web enthusiast, I built Sharp GUI to bridge this gap. Run **[a one-click deployment](#-quick-start)** on a computer, then use browsers on Android, Windows, Mac or VR devices on your local network to create, explore and share 3D spatial memories. This is a hobbyist exploration, built for everyone to enjoy.

<br>

![Sharp GUI](https://img.shields.io/badge/Sharp-GUI-0071e3?style=for-the-badge&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61dafb?style=for-the-badge&logo=react&logoColor=black)
![Flask](https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white)
![Three.js](https://img.shields.io/badge/Three.js-Viewer-000000?style=for-the-badge&logo=threedotjs&logoColor=white)

Built on [Apple ml-sharp](https://github.com/apple/ml-sharp). No cloud uploads needed. **Host Locally, Access Everywhere.** Beyond generating and viewing 3D models, Sharp GUI can organize generated results, imported models, and local / external-drive / NAS media into a lightweight model asset library and LAN photo gallery.

[Features](#-features) •
[Preview](#-preview) •
[Quick Start](#-quick-start) •
[3D Controls](#3d-interaction-controls) •
[LAN Access Gate](#-lan-access-gate-and-privacy-boundary) •
[Documentation](#-documentation)

</div>

> [!WARNING]
> **No content restrictions for local deployment** - Users are fully responsible for generated content. Please comply with local laws and regulations. See [Disclaimer](#disclaimer).

---

## 📑 Table of Contents

<table align="center">
<tr>
<td width="190" align="center" valign="top">

### 🚀

**Getting Started**

<sub>Up and running in minutes</sub>

<br>

[Recent Highlights](#-recent-highlights)<br>
[Quick Start](#-quick-start)<br>
[Usage Guide](docs/usage.en.md)<br>
[Version & Updates](#version-and-updates)

</td>
<td width="190" align="center" valign="top">

### ✨

**Features & Design**

<sub>What Sharp GUI can do</sub>

<br>

[Feature Highlights](#-features)<br>
[Interface Preview](#-preview)

</td>
<td width="190" align="center" valign="top">

### ⚙️

**Config & Security**

<sub>Customize and lock down</sub>

<br>

[Configuration](docs/deployment.en.md#%EF%B8%8F-configuration)<br>
[Video Reconstruction Settings](docs/deployment.en.md#video-reconstruction-configuration)<br>
[LAN Access Gate](#-lan-access-gate-and-privacy-boundary)

</td>
<td width="190" align="center" valign="top">

### 🛠️

**Build & Community**

<sub>Hack, ship, and contribute</sub>

<br>

[Architecture](docs/development.en.md#%EF%B8%8F-architecture)<br>
[Developer Guide](docs/development.en.md)<br>
[Release History](#-release-history)<br>
[Contributing](#-contributing) · [Credits](#-acknowledgements)

</td>
</tr>
</table>

<div align="center"><sub>📄 <a href="#-license">License</a> &nbsp;·&nbsp; ⚠️ <a href="#disclaimer">Disclaimer</a></sub></div>

---

## 🆕 Recent Highlights

<details open>
<summary><b>Click to collapse — user-facing highlights</b></summary>

<br>

**🎥 Rebuilt Video Pipeline · Better Quality and Efficiency** — Frame extraction, camera alignment, training, and export have been rebuilt around fixed source-frame planning, COLMAP, and official Brush. Compared with the old route, this substantially improves detail and edges while reducing processing time. High retains a 1920-pixel long edge; Extreme retains 3840 pixels with a 12 GB budget. High-quality resolution is not sacrificed for speed. Includes quality presets, alignment checks, source replay, and PLY / SPZ export. The [same-footage quality and timing review (Chinese)](docs/video-reconstruction-quality.md) records the validation scope; runtime varies with footage, settings, and hardware.

**✂️ Model Editing** — Open the editor from the asset library or viewer. Clean up splats with rectangle, sphere, and box selections; drag selection boundaries, calibrate the origin and orientation, undo / redo, and save a copy or overwrite the model. See the [editing guide and supported formats (Chinese)](docs/model-editor.md).

**🎬 Export Animation** — Record camera keyframes, choose a motion curve, inspect the camera path and viewing angles in a 3D overview, and export 1080p / 4K video. See the [animation export guide (Chinese)](docs/camera-animation.md).

**🔗 Linked Media and Models** — Blue 3D badges lead from source media to generated models, with version selection and a default result. The pinned Model Sources album gathers linked photos and videos. See the [linking guide (Chinese)](docs/model-source-gallery.md).

**📦 Model Asset Library** — Browse generated models and imported `.ply/.spz/.splat/.rad` assets together with filters, sorting, cursor-based incremental loading, recent models, a details panel, batch import, download, and delete. The preferred open/download format follows Settings and falls back to available files.

**🗂️ Local Media Gallery** — Configure local, external-drive, or NAS folders as albums. Browse, filter, preview, and download photos and videos together; photos can be converted to 3D one by one or in batches, while videos can be played, scrubbed, and viewed fullscreen.

**📤 Upgraded Standalone HTML Sharing** — The rebuilt viewer preserves model orientation and the saved initial view, with full-model framing, orbit, background switching, mobile controls, and bilingual help. The model and viewer are embedded in one offline HTML file. See the [sharing guide (Chinese)](docs/standalone-sharing.md).

**📦 Windows Full Portable Bundles** — Core bundles `cu128-rtx50` and `cu126-mainstream` ship Python + PyTorch + model cache out of the box, with an additional `cu128-rtx50-video-recon` bundle for RTX 50 video reconstruction (downloaded from the cloud-drive link in the Release notes, with matching `.sha256.txt`).

**⚙️ Grouped Settings and Persistent Configuration** — Settings are grouped into General, Access & Security, Viewer, Gallery, Video Reconstruction, and Updates. System-user configuration lets a new complete package reuse the original workspace, models, and albums; recovery from an older package is also available. See the [configuration and recovery guide (Chinese)](docs/global-configuration.md).

**🔐 Safer LAN Access** — Optional access-code gate, real LAN bind toggle, sensitive-file protection, and debug mode off by default make long-running home LAN use safer.

Full release notes → **[Latest Release](https://github.com/lueluelue12138/sharp-gui/releases/latest)**

</details>

---

## ✨ Features

### 🏠 Host Once, Access Anywhere

No need to install apps on every device. Run Sharp GUI on one computer, and any phone, tablet or VR device on your LAN can access it instantly via browser. HTTPS provides the secure context required by features such as gyroscope controls; availability depends on the browser, device and permissions.

### 🚀 Core Features

| Feature                    | Description                                                                                                                                                              |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **📸 Image to 3D**         | Upload a single image; Apple ML-Sharp generates a 3D Gaussian Splatting model. The 2.62 GiB model is pre-downloaded during install.                                          |
| **🎥 Video 3DGS Reconstruction** | Create static Gaussian Splat models from album or dropped videos using COLMAP + Brush, with quality presets, task stages, thumbnails and source replay. |
| **🖼️ Modern Workflow**     | Multi-select / drag-and-drop upload, virtualized gallery, in-app original viewer, smart task queue (2s while active, 10s idle), slide-out delete, cancellable jobs.      |
| **📦 Model Asset Library** | Browse generated and imported models together, with `.ply/.spz/.splat/.rad`, filters, sorting, details metadata, recent models, batch import, and cursor-based incremental loading. |
| **🗂️ Local Media Gallery** | Configure multiple local/NAS folders as albums, browse and filter photos/videos together, preview and download media, convert photos to 3D, play videos, and start video reconstruction. |
| **👁️ Real-time Viewer**    | Three.js + Spark 2.0 WASM-accelerated viewer with mouse / touch / keyboard (WASD) / gyroscope controls, click-to-focus with a GPU focus ring, quick transform panel.     |
| **✂️ Model Editing**       | Rectangle / sphere / box selection, draggable values and boundaries, splat cleanup, origin and orientation calibration, undo / redo, and copy or overwrite saving with source links retained. |
| **🎬 Export Animation**    | Camera keyframes, five motion curves, 3D path and frustum preview, and silent WebM / MP4 export at 1080p / 4K, landscape / portrait, and 24 / 30 / 60 fps. |
| **🔗 Linked Source Media** | Blue 3D badges, linked-model navigation, multiple versions and default results, plus a pinned Model Sources album grouped by source. |
| **🎭 Reveal Effects**      | Magic / Spread / Unroll / Twister / Rain entrance animations with replay support.                                                                                        |
| **📱 Mobile Optimized**    | Phones / tablets get gyroscope controls (iOS-style indicator ball), virtual joystick, touch gestures, and a drawer-style sidebar.                                        |
| **🥽 VR/AR Preview**       | WebXR VR mode + AR Passthrough on Quest 3/Pro and similar headsets, with controller / touch input.                                                                       |
| **📤 One-Click Share**     | Export one offline HTML containing the model and Spark 2.0 viewer, preserving orientation and the initial view, with full-model framing, orbit, backgrounds, and mobile controls. |
| **🎮 GPU Acceleration**    | Auto-detects NVIDIA GPUs and matches a CUDA-enabled PyTorch (cu118 / cu126 / cu128) for noticeably faster inference.                                                     |
| **🔄 Safe Self-Update**    | Settings shows the release and exact commit, with Stable / Latest checks and compatible one-click code updates; failures restore automatically and portable bundles need no system Git. |
| **🔐 Security & Privacy**  | Fully local data, one-click self-signed SSL, optional LAN access gate (HttpOnly cookie + access code + brute-force backoff).                                             |
| **🚀 One-Click Deploy**    | Auto-configures Python / Git, installs deps, pre-downloads models, generates HTTPS certs, and shows skeleton progress. Ready out of the box.                             |

### 🎨 Apple-Style Interface

Glass panels, system fonts, light and dark themes, smooth transitions and responsive controls provide a consistent desktop and mobile experience.

---

## 📷 Preview

### Main Interface

<p align="center">
  <img src="docs/images/main.png" width="800" alt="Main Interface">
</p>

<p align="center"><i>Recent models + 3D spatial preview + glassmorphism control bar</i></p>

### Local Media Gallery

<p align="center">
  <img src="docs/images/photo-gallery.png" width="800" alt="Local media gallery interface">
</p>

<p align="center"><i>Multi-folder albums, mixed photo/video browsing, media preview, multi-select to 3D</i></p>

### Video 3DGS Reconstruction

<p align="center">
  <img src="docs/images/video-reconstruction-current.jpg" width="800" alt="Video reconstruction settings dialog">
</p>

<p align="center"><i>Open the reconstruction dialog from an album video or dropped video, then choose mode, quality, custom parameters, and dependency status</i></p>

<p align="center">
  <img src="docs/images/demo-video-reconstruction.webp" width="800" alt="Animated training preview">
</p>

<p align="center"><i>Recorded training preview; reconstruction settings are shown in the current launch panel above</i></p>

### Model Editing

<p align="center">
  <img src="docs/images/model-editor.jpg" width="800" alt="Model editor with box selection, draggable boundaries, and live parameters">
</p>

<p align="center"><i>Clean up splats, drag selection boundaries, calibrate the origin and orientation, and save a copy or overwrite the model</i></p>

### Animation Export and Path Preview

<p align="center">
  <img src="docs/images/animation-path.jpg" width="800" alt="Export animation with a multi-keyframe orbit, height and distance changes, camera frustums, and playback timeline">
</p>

<p align="center"><i>Seven shots combine orbit, height, and distance changes; blue marks keyframes and the path, while the white frustum follows the timeline. Helpers stay out of the exported video</i></p>

### Mobile Adaptation

<p align="center">
  <img src="docs/images/mobile.webp" height="400" alt="Mobile">&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/images/pad.png" height="400" alt="Tablet">
</p>

<p align="center">
  <i>Left: Mobile drawer sidebar | Right: Tablet split layout</i>
</p>

### 🎬 Camera Movement Controls

<p align="center">
  <img src="docs/images/demo-wasd.webp" width="380" alt="WASD Controls">&nbsp;&nbsp;&nbsp;&nbsp;
  <a href="docs/images/demo-joystick-2.mp4"><img src="docs/images/joystick-preview.jpg" width="380" alt="Virtual Joystick"></a>
</p>

<p align="center">
  <i>WASD/QE keyboard movement and mobile virtual joystick — click the joystick image for the MP4 demo</i>
</p>

### 🎬 Batch Upload + Queue Processing

<p align="center">
  <img src="docs/images/demo-upload.gif" width="600" alt="Upload Demo">
</p>

<p align="center"><i>Drag multiple images to sidebar, queue updates in real-time</i></p>

### 🎬 Gyroscope Control (Mobile)

<p align="center">
  <img src="docs/images/demo-gyro.webp" height="400" alt="Gyro Demo">
</p>

<p align="center"><i>Tilt phone to control view, iOS-style real-time indicator ball</i></p>

### 🎬 One-Click Export & Share

<p align="center">
  <img src="docs/images/share-preview.jpg" width="800" alt="Current standalone HTML sharing viewer">
</p>

<p align="center"><i>Export one HTML file for offline viewing in a WebGL2-capable browser, with saved framing, orbit and background controls</i></p>

---

## 🚀 Quick Start

Single-image reconstruction can run on Windows, macOS and Linux using NVIDIA CUDA, Apple Silicon MPS or CPU. See the [platform validation table](docs/deployment.en.md#system-requirements). Video reconstruction has completed end-to-end validation on **Windows + RTX 5070 Ti Laptop (12 GB)**.

### Windows Full Portable Bundle

Use [GitHub Releases](https://github.com/lueluelue12138/sharp-gui/releases) for versions, download links and SHA256 files, or open the [portable bundle folder](https://pan.quark.cn/s/94f4acaada40). Choose by GPU and purpose:

| Purpose | Bundle |
| --- | --- |
| RTX 50 series, single-image and core features | `cu128-rtx50` |
| RTX 50 series, including video reconstruction tools | `cu128-rtx50-video-recon` |
| Mainstream NVIDIA below RTX 50, single-image and core features | `cu126-mainstream` |

Download the ZIP and matching `.sha256.txt`, verify the checksum, extract, then launch `portable-run.bat`. Full portable bundles target NVIDIA GPUs; other devices can install from source.

### Install from Source

The repository includes the built frontend. Ordinary use does not require Node.js.

```bash
git clone https://github.com/lueluelue12138/sharp-gui.git
cd sharp-gui
```

| Platform | First-Time Installation |
| --- | --- |
| Windows | `install.bat` |
| Linux / macOS | `./install.sh` |

A generic Release ZIP also requires the install script; it is different from a full portable bundle. Initial installation downloads dependencies and the approximately 2.62 GiB single-image model. See [installation, configuration and LAN access](docs/deployment.en.md) for full steps.

<a id="video-reconstruction-manual-environment-setup"></a>

Video reconstruction also needs COLMAP, Brush and FFmpeg. Choose the video bundle or follow the [video environment setup guide](docs/deployment.en.md#video-reconstruction-manual-environment-setup).

### Start the App

Run from the extracted portable bundle or project root. Once installed, start the app directly for everyday use.

| Installation / Platform | Start Command |
| --- | --- |
| Windows full portable bundle | Double-click `portable-run.bat` |
| Windows source / generic Release ZIP | `run.bat` |
| Linux / macOS | `./run.sh` |

### Access and Updates

After startup, visit **https://127.0.0.1:5050**. Other devices on your LAN use the host computer's IP. See [HTTPS and sensor setup](docs/deployment.en.md#enable-https-recommended).

<a id="version-and-updates"></a>

Check **Settings → Updates**: **Stable** uses formal releases, while **Latest** uses newer main-branch code with less testing. Supported source installations and managed portable bundles can install compatible updates; older bundles need a new full package first. Workspaces, models and configuration are preserved; runtime changes may require a new complete bundle. See [updates and CLI commands](docs/deployment.en.md#version-and-updates).

---

<a id="3d-interaction-controls"></a>

## 🎮 3D Interaction Controls

### Basic Operations

| Action      | Desktop          | Mobile              |
| ----------- | ---------------- | ------------------- |
| Rotate View | Left-click drag  | Single finger swipe |
| Pan         | Right-click drag | Two finger pan      |
| Zoom        | Scroll wheel     | Pinch               |
| Fine Zoom   | Shift + Scroll   | -                   |
| Lock Focus  | Click on model   | Tap on model        |

### Camera Movement

| Control              | Description                                           |
| -------------------- | ----------------------------------------------------- |
| **WASD / QE**        | Keyboard camera pan (forward/back/left/right/up/down) |
| **Shift + WASD**     | Fast movement mode                                    |
| **Alt + WASD**       | Precision movement mode                               |
| **Virtual Joystick** | Mobile touch pan (tap Move button to enable)          |

### Special Modes

| Mode           | Action                          | Description                                                                |
| -------------- | ------------------------------- | -------------------------------------------------------------------------- |
| Quick Controls | Tap the gear button             | Adjust model scale, position, rotation, interaction direction, and quality |
| Reveal Effects | Use the right-side effects rail | Switch or replay Magic / Spread / Unroll / Twister / Rain                  |
| Gyroscope      | Tap "Gyro" button               | Tilt phone to control view                                                 |
| Front View     | Tap "Front View" button         | Lock to front view, tap again free                                         |
| Reset          | Tap "Reset" button              | Restore initial view                                                       |
| Fullscreen     | Tap "Fullscreen" button         | Immersive preview                                                          |
| VR Preview     | Tap "VR" button                 | Enter VR mode (requires VR device)                                         |
| AR Preview     | Tap "AR" button                 | AR Passthrough overlay 3D model                                            |
| Reset          | Press "R" key                   | Quick reset camera to initial view                                         |

---

## 🔐 LAN Access Gate and Privacy Boundary

- **Access settings**: Access & security is the second Settings category. Configure LAN access and an access code there. The gate is off by default; once enabled, other devices must unlock first.
- **Management**: deleting models, managing albums and changing settings require local access. Unlocked remote devices can browse, download and share; remote generation requires a separate opt-in.
- **Data locations**: configuration lives in the system user directory; models and albums use the selected workspace. Keep the data directory when replacing a package. See [configuration storage and recovery (Chinese)](docs/global-configuration.md).
- **Sharing**: standalone HTML contains model data and cannot be recalled through the app after sending. It does not include source images/videos or workspace paths.

The full permission matrix, HTTPS, reverse-proxy caveats and deployment notes are in the [LAN access guide](docs/deployment.en.md#-lan-access-gate-and-privacy-boundary).

---

<a id="-usage"></a>
<a id="generate-3d-models-from-video"></a>
<a id="-configuration"></a>
<a id="-developer-guide"></a>

## 📚 Documentation

| Guide | Contents |
| --- | --- |
| [Usage](docs/usage.en.md) | Detailed steps for single-image / video generation, assets, albums, editing, animation and sharing |
| [Installation, configuration and LAN access](docs/deployment.en.md) | Install options, updates, workspace, video tools, HTTPS, permissions and deployment |
| [Developer guide](docs/development.en.md) | Project structure, stack, frontend development, environment variables and releases |

In-depth guides (Chinese): [model editing](docs/model-editor.md) · [animation export](docs/camera-animation.md) · [gallery/model links](docs/model-source-gallery.md) · [standalone HTML sharing](docs/standalone-sharing.md) · [video quality and timing review](docs/video-reconstruction-quality.md)

---

## 🤝 Acknowledgements

- [Apple ML-Sharp](https://github.com/apple/ml-sharp) - Core 3D generation model
- [Spark](https://github.com/nickthetimid/spark) - WASM-accelerated Gaussian Splatting rendering engine (Spark 2.0)
- [Gaussian Splats 3D](https://github.com/mkkellogg/GaussianSplats3D) - Original Three.js Gaussian Splatting renderer (Legacy version)
- [antimatter15/splat](https://github.com/antimatter15/splat) - Splat format conversion reference

---

## 🙋 Contributing

Issues and Pull Requests are welcome!

- 🐛 **Bug Reports** - Submit issues on [GitHub Issues](https://github.com/lueluelue12138/sharp-gui/issues)
- 💡 **Feature Requests** - Discuss new feature ideas via Issues
- 🔧 **Code Contributions** - Fork the project and submit PRs
- 🖥️ **Platform Testing** - If you've tested on NVIDIA GPU or other unverified environments, we'd love your feedback!

---

## 📜 Release History

Full release notes, feature evolution, pre-release channel, and download links:

- 📦 **[GitHub Releases](https://github.com/lueluelue12138/sharp-gui/releases)** — every release with notes
- 🆕 **[Latest](https://github.com/lueluelue12138/sharp-gui/releases/latest)** — current stable release
- 🧪 **[Pre-release Channel](https://github.com/lueluelue12138/sharp-gui/releases?q=prerelease%3Atrue)** — early access to upcoming features

---

<a name="disclaimer"></a>

## ⚠️ Disclaimer

Since local deployment has **no content restrictions**, 3D models generated by this project are created by users using AI tools. **Users are solely responsible for the generated content**, which is unrelated to this open source project and its developers.

**It is strictly prohibited to use this tool to generate or distribute any illegal, infringing, or inappropriate content.**

---

## 📄 License

This project is open source under the MIT License.

When portable bundles include MinGit or other third-party components, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for their provenance, versions, and license locations.

Note: the Sharp GUI code's MIT License does not cover the ML-Sharp models. Those models remain under Apple's separate [Model License](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL), for non-commercial use only.

---

<div align="center">

**If you find this useful, please give a ⭐ Star!**

Made with ❤️ by [lueluelue12138](https://github.com/lueluelue12138)

</div>
