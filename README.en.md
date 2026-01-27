# Sharp GUI

<p align="right">
  <a href="README.md">🇨🇳 中文</a> | <a href="README.en.md">🇺🇸 English</a>
</p>

<div align="center">

**A Beautiful 3D Gaussian Splatting GUI**

<img src="assets/logo.png" alt="Sharp GUI Logo" width="200" />

<br>

**💡 Background**

The "Spatial Photos" feature in iOS 26 offers an amazing immersive experience, but is currently limited to the Apple ecosystem.

As a Web enthusiast, I built Sharp GUI to bridge this gap. My goal is to let anyone—whether on Android, Windows, or Mac—**[deploy with one click](#-quick-start)** and create and share 3D spatial memories directly via a browser on their local network. This is a hobbyist exploration, built for everyone to enjoy.

<br>

![Sharp GUI](https://img.shields.io/badge/Sharp-GUI-0071e3?style=for-the-badge&logo=apple&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Backend-000000?style=for-the-badge&logo=flask&logoColor=white)
![Three.js](https://img.shields.io/badge/Three.js-Viewer-000000?style=for-the-badge&logo=threedotjs&logoColor=white)

Built on [Apple ml-sharp](https://github.com/apple/ml-sharp). No cloud uploads needed. **Host Locally, Access Everywhere.**

[Features](#-features) •
[Preview](#-preview) •
[Quick Start](#-quick-start) •
[Usage](#-usage) •
[Architecture](#-architecture)

</div>

> [!WARNING]
> **No content restrictions for local deployment** - Users are fully responsible for generated content. Please comply with local laws and regulations. See [Disclaimer](#⚠️-disclaimer).

---

## ✨ Why Sharp GUI?

### 🏠 Host Once, Access Anywhere

No need to install apps on every device. Run Sharp GUI on one computer, and any phone or tablet on your LAN can access it instantly via browser. Full HTTPS support ensures features like gyroscope work perfectly on all devices.

### 🚀 Core Features

| Feature                  | Description                                                       |
| ------------------------ | ----------------------------------------------------------------- |
| **📸 Image to 3D**       | Upload any image, AI generates 3D Gaussian Splatting model        |
| **🖼️ Batch Processing**  | Multi-select/drag-drop upload with smart queue scheduling         |
| **👁️ Real-time Preview** | High-performance viewer with Three.js + Gaussian Splats 3D        |
| **📤 One-Click Share**   | Export as standalone HTML, viewable without server                |
| **📱 Mobile Optimized**  | Perfect adaptation for phones/tablets with gyroscope support      |
| **🚀 One-Click Deploy**  | Auto-configures Python env, downloads deps, generates HTTPS certs |

### 🎨 Apple-Style UI Design

Built with Apple Human Interface Guidelines for a premium user experience:

| Element                 | Description                                                   |
| ----------------------- | ------------------------------------------------------------- |
| **Glass Morphism**      | Global `backdrop-filter: blur()` with translucent backgrounds |
| **SF Pro Fonts**        | Apple system font stack for native rendering                  |
| **Particle Background** | Canvas-drawn floating particles for tech aesthetics           |
| **Smooth Animations**   | All interactions tuned with `cubic-bezier` easing             |
| **Dark Mode**           | Adaptive system dark mode support                             |

### 🎯 UX Optimizations

- **Skeleton Loading** - Smooth gradient animation while loading thumbnails
- **Smart Polling** - 2s polling when active, 10s when idle
- **Drag & Drop Upload** - Drop images directly into sidebar
- **Drag & Drop Preview** - Drop .ply/.splat models to preview directly
- **Queue Management** - Cancel/delete pending tasks
- **Progress Bar** - Real-time loading percentage
- **Delete Animation** - Smooth slide-out effect
- **Collapsible Controls** - Bottom bar can be collapsed for more preview space

### 🎮 Camera Controls

| Control              | Description                                           |
| -------------------- | ----------------------------------------------------- |
| **WASD/QE**          | Keyboard camera pan (forward/back/left/right/up/down) |
| **Shift+WASD**       | Precision movement mode                               |
| **Shift+Scroll**     | Precision zoom control                                |
| **Virtual Joystick** | Mobile touch pan (tap Move button to enable)          |
| **Gyroscope**        | Tilt phone to preview (tap Gyro button to enable)     |

<!-- TODO: Add camera controls GIF -->
<!-- ![Camera Controls Demo](docs/camera-controls.gif) -->

### 🔧 Advanced Features

- **🔒 HTTPS Support** - Auto-generated self-signed certificates for LAN access
- **📦 File Optimization** - PLY → Splat format conversion, **43% smaller**
- **🧹 Auto Cleanup** - Completed tasks auto-cleaned after 1 hour
- **⚙️ Configurable Paths** - Custom workspace folder
- **🖥️ Fullscreen Mode** - Immersive 3D preview
- **🌐 Internationalization** - Chinese/English bilingual UI, auto-detects browser language, manual toggle

---

## 📷 Preview

### Main Interface

<p align="center">
  <img src="docs/images/main.png" width="800" alt="Main Interface">
</p>

<p align="center"><i>Sidebar gallery + 3D model preview + glassmorphism control bar</i></p>

### Mobile Adaptation

<p align="center">
  <img src="docs/images/mobile.png" height="400" alt="Mobile">&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/images/tablet.png" height="400" alt="Tablet">
</p>

<p align="center">
  <i>Left: Mobile drawer sidebar | Right: Tablet split layout</i>
</p>

### Feature Demos

<!-- <details> -->
<summary><b>🎬 Camera Movement Controls</b></summary>

<p align="center">
  <img src="docs/images/demo-wasd.gif" height="300" alt="WASD Controls">&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="docs/images/demo-joystick.gif" height="300" alt="Virtual Joystick">
</p>

<p align="center">
  <i>Left: WASD/QE keyboard movement (Shift for precision) | Right: Mobile virtual joystick</i>
</p>

<!-- </details> -->

<!-- <details> -->
<summary><b>🎬 Batch Upload + Queue Processing</b></summary>

<p align="center">
  <img src="docs/images/demo-upload.gif" width="600" alt="Upload Demo">
</p>

<p align="center"><i>Drag multiple images to sidebar, queue updates in real-time</i></p>

<!-- </details> -->

<!-- <details> -->
<summary><b>🎬 Gyroscope Control (Mobile)</b></summary>

<p align="center">
  <img src="docs/images/demo-gyro.gif" height="400" alt="Gyro Demo">
</p>

<p align="center"><i>Tilt phone to control view, iOS-style real-time indicator ball</i></p>

<!-- </details> -->

<!-- <details> -->
<summary><b>🎬 One-Click Export & Share</b></summary>

<p align="center">
  <img src="docs/images/demo-share.gif" width="600" alt="Share Demo">
</p>

<p align="center"><i>Click Share to export standalone HTML, double-click to open in any browser</i></p>

<!-- </details> -->

---

## 🎨 Design Highlights

- 🪟 **Glass Morphism** - Frosted glass control bar with `backdrop-filter: blur(30px)`
- ✨ **Dynamic Particles** - Canvas-rendered floating tech-style particles
- 🎯 **iOS-Style Indicator** - Mobile gyroscope real-time feedback ball
- 🎬 **Fluid Animations** - All interactions with `cubic-bezier` easing curves
- 📱 **Responsive Design** - Perfect for desktop/tablet/mobile

---

## 🚀 Quick Start

### System Requirements

| Platform                  | Inference     | Video Rendering | Status        |
| ------------------------- | ------------- | --------------- | ------------- |
| **macOS Apple Silicon**   | ✅ MPS        | ❌              | ✅ Verified   |
| **Linux x86_64 no GPU**   | ✅ CPU        | ❌              | ✅ Verified   |
| **Linux x86_64 + NVIDIA** | ✅ CUDA       | ✅              | ❓ Unverified |
| **macOS Intel**           | ✅ CPU        | ❌              | ❓ Unverified |
| **Windows**               | ❓ Unverified | ❓              | ❓ Unverified |

> 📢 **No GPU? No problem!** 3D model generation works on pure CPU. Only video rendering requires CUDA.  
> 👉 Unverified platforms should theoretically work. Report issues on [GitHub Issues](https://github.com/lueluelue12138/sharp-gui/issues).

### Option 1: Download Pre-built Package (Recommended for Users)

Download the latest version from [Releases](https://github.com/lueluelue12138/sharp-gui/releases):

```bash
# 1. Download and extract
unzip sharp-gui-v1.0.0.zip
cd sharp-gui

# 2. Run install script (Python only)
./install.sh      # Linux/macOS
# or
install.bat       # Windows

# 3. Start server
./run.sh          # Linux/macOS
# or
run.bat           # Windows
```

> 💡 Pre-built packages include compiled frontend, **no Node.js required**. Ready to use out of the box.  
> ⚠️ Note: Pre-built packages are based on stable releases and may not include the latest development features.

### Option 2: Install from Source (Developers / Latest Features)

```bash
# 1. Clone project
git clone https://github.com/lueluelue12138/sharp-gui.git
cd sharp-gui

# 2. Run install script (auto-clones ml-sharp and configures environment)
./install.sh      # Linux/macOS
# or
install.bat       # Windows

# 3. (Optional) To modify frontend, install Node.js 18+ then run:
./build.sh        # Build frontend
```

> 💡 The install script auto-generates HTTPS certificates. HTTPS mode is recommended for full functionality.

### Start Server

```bash
./run.sh          # Linux/macOS (React version)
./run.sh --legacy # Use original single-file version
# or
run.bat           # Windows
```

Access **https://127.0.0.1:5050 (recommended)** or **http://127.0.0.1:5050** 🎉

---

## 📖 Usage

### Generate 3D Models

1. **Upload Image** - Click "Generate New" or drag images to sidebar
2. **Wait for Processing** - Watch queue progress (first run downloads ~500MB model)
3. **Preview Model** - Click gallery items to view 3D

### 3D Interaction Controls

| Action        | Desktop                                  | Mobile                      |
| ------------- | ---------------------------------------- | --------------------------- |
| Rotate View   | Left-click drag                          | Single finger swipe         |
| Zoom          | Scroll / Shift+Scroll (fine)             | Pinch                       |
| Gyroscope     | -                                        | Enable Gyro then tilt phone |
| Reset         | Click "Reset" button                     | Same                        |
| Toggle Limits | Click "Front View" for free/limited mode | Same                        |

### Export & Share

Click **Share** button to generate a standalone HTML file:

- 📦 Complete 3D viewer included (Three.js + Gaussian Splats 3D)
- 🌐 No server needed, double-click to open in browser
- 📉 Optimized size: PLY → Splat format, 43% smaller
- 🔒 Includes disclaimer about content responsibility

---

## ⚙️ Configuration

### Custom Workspace

Configure via UI settings or edit `config.json` (generated on first run):

```json
{
  "workspace_folder": "/path/to/workspace"
}
```

The system auto-creates:

- `inputs/` - Uploaded images
- `outputs/` - Generated models

### Enable HTTPS (Recommended)

HTTPS enables **gyroscope on LAN devices** (browsers require secure context for sensor APIs).

The install script auto-generates certificates. For manual generation:

```bash
python generate_cert.py
```

> 💡 **Windows Users**: Install [Git for Windows](https://git-scm.com/download/win) or OpenSSL first.

After generating, restart and access via `https://`:

| Mode      | Local                  | LAN               | Gyroscope     |
| --------- | ---------------------- | ----------------- | ------------- |
| **HTTPS** | https://127.0.0.1:5050 | https://[IP]:5050 | ✅ Available  |
| HTTP      | http://127.0.0.1:5050  | http://[IP]:5050  | ❌ Local only |

First HTTPS access shows certificate warning (self-signed), click "Continue" to proceed.

---

## 🏗️ Architecture

### Project Structure

```
sharp-gui/
├── 📄 app.py                 # Flask backend + task queue system
├── 📄 install.sh/bat         # One-click install scripts
├── 📄 run.sh/bat             # Startup scripts (supports --legacy flag)
├── 📄 build.sh/bat           # Frontend build scripts
├── 📄 release.sh/bat         # Release packaging scripts
├── 📄 generate_cert.py       # SSL certificate generator
├── 📁 frontend/              # React modern frontend (v1.0.0+)
├── 📁 templates/             # Original single-file frontend (Legacy)
├── 📁 static/lib/            # Three.js + Gaussian Splats 3D
├── 📁 ml-sharp/              # (after install) Apple ML-Sharp core
├── 📁 inputs/                # Input images
└── 📁 outputs/               # Output models (.ply)
```

### Frontend Architecture (React)

```
frontend/
├── 📁 src/
│   ├── 📁 api/               # API client (gallery, tasks, settings)
│   ├── 📁 components/
│   │   ├── 📁 common/        # Common components (Button, Modal, Loading, ParticleBackground)
│   │   ├── 📁 gallery/       # Gallery components (GalleryList, GalleryItem)
│   │   ├── 📁 layout/        # Layout components (Sidebar, ControlsBar, TaskQueue, Settings)
│   │   └── 📁 viewer/        # Viewer components (ViewerCanvas, VirtualJoystick, GyroIndicator)
│   ├── 📁 hooks/             # Custom Hooks (useViewer, useGyroscope, useKeyboard)
│   ├── 📁 i18n/              # Internationalization (zh.json, en.json)
│   ├── 📁 store/             # Zustand state management
│   ├── 📁 styles/            # Global styles (variables, animations)
│   ├── 📁 types/             # TypeScript type definitions
│   └── 📁 utils/             # Utility functions
├── 📄 vite.config.ts         # Vite config (code splitting)
└── 📁 dist/                  # Build output
```

### Tech Stack

| Layer            | Technology                                          |
| ---------------- | --------------------------------------------------- |
| **Frontend**     | React 19 + TypeScript + Vite / Single-file (Legacy) |
| **State**        | Zustand                                             |
| **i18n**         | i18next + react-i18next                             |
| **Styling**      | CSS Modules + Apple Glass Morphism                  |
| **Backend**      | Python 3.10+, Flask, multi-threaded task queue      |
| **AI Engine**    | Apple ML-Sharp (PyTorch, gsplat)                    |
| **3D Rendering** | Three.js + Gaussian Splats 3D                       |

### Performance Optimizations

| Optimization              | Description                                                                      |
| ------------------------- | -------------------------------------------------------------------------------- |
| **Code Splitting**        | Vite manualChunks: three.js (489KB), gaussian-splats (249KB), react-vendor (4KB) |
| **Thumbnail System**      | Auto-generated 200px JPEG thumbnails, saves bandwidth                            |
| **Smart Polling**         | Active 2s polling, idle 10s, saves resources                                     |
| **Format Conversion**     | PLY → Splat export conversion, 43% smaller file size                             |
| **Memory Cleanup**        | Completed tasks auto-removed from memory after 1 hour                            |
| **Progress Optimization** | Progress bar only moves forward, no visual jumping                               |

---

## 🛠️ Developer Guide

### Frontend Development

```bash
# Install dependencies
cd frontend
npm install

# Development mode (hot reload)
npm run dev

# Build for production
npm run build
# Or use project script
./build.sh
```

### Switch Frontend Version

```bash
./run.sh           # Use React modern version (default)
./run.sh --legacy  # Use original single-file version
```

### Create Release Package

```bash
# Auto build and package
./release.sh v1.0.0

# Output: sharp-gui-v1.0.0.zip (includes pre-built frontend)
```

---

## 🤝 Acknowledgements

- [Apple ML-Sharp](https://github.com/apple/ml-sharp) - Core 3D generation model
- [Gaussian Splats 3D](https://github.com/mkkellogg/GaussianSplats3D) - Three.js Gaussian Splatting renderer
- [antimatter15/splat](https://github.com/antimatter15/splat) - Splat format conversion reference

---

## 🙋 Contributing

Issues and Pull Requests are welcome!

- 🐛 **Bug Reports** - Submit issues on [GitHub Issues](https://github.com/lueluelue12138/sharp-gui/issues)
- 💡 **Feature Requests** - Discuss new feature ideas via Issues
- 🔧 **Code Contributions** - Fork the project and submit PRs

If you've tested on other platforms (Linux/Windows), feedback is appreciated!

---

## ⚠️ Disclaimer

Since local deployment has **no content restrictions**, 3D models generated by this project are created by users using AI tools. **Users are solely responsible for the generated content**, which is unrelated to this open source project and its developers.

**It is strictly prohibited to use this tool to generate or distribute any illegal, infringing, or inappropriate content.**

---

## 📄 License

This project is open source under the MIT License.

Note: ML-Sharp models have a separate [Model License](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL), for non-commercial use only.

---

<div align="center">

**If you find this useful, please give a ⭐ Star!**

Made with ❤️ by [lueluelue12138](https://github.com/lueluelue12138)

</div>
