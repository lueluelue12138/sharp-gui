# Installation, Configuration and LAN Access

[中文](deployment.md) · [Back to README](../README.en.md) · [Usage](usage.en.md)

This guide collects full installation options, runtime preparation, configuration and access boundaries. For a shorter start, use the [README](../README.en.md#-quick-start).

## 🚀 Quick Start

### System Requirements

| Platform                    | Inference Backend | Status        |
| --------------------------- | ----------------- | ------------- |
| **macOS Apple Silicon**     | ✅ MPS            | ✅ Verified   |
| **Windows x86_64**          | ✅ CPU            | ✅ Verified   |
| **Windows x86_64 + NVIDIA** | ✅ CUDA           | ✅ Verified   |
| **Linux x86_64**            | ✅ CPU            | ✅ Verified   |
| **Linux x86_64 + NVIDIA**   | ✅ CUDA           | ❓ Unverified |
| **macOS Intel**             | ✅ CPU            | ❓ Unverified |

> 🎥 **Current video reconstruction platform**: Video 3DGS reconstruction has currently only been verified end-to-end on **Windows + NVIDIA RTX 5070 Ti Laptop GPU (12GB VRAM)**. Other Windows NVIDIA GPUs may work, but Linux, macOS, CPU, and MPS video reconstruction are not yet verified.
>
> 🚀 **NVIDIA GPU recommended**: 3D Gaussian Splatting inference is compute-heavy. CUDA typically delivers **multiple-x to ~10x** speedups over pure CPU, with a noticeably better experience.
>
> 💡 **CPU-only still works**: inference runs fine without a GPU, just slower per image. Apple Silicon users get a near-GPU experience via the MPS backend.
>
> 🛠️ **Zero manual setup**: when an NVIDIA GPU is present, the install script detects your driver and installs the matching CUDA-enabled PyTorch (cu118 / cu126 / cu128).
>
> 🎥 **Video reconstruction environment requires a separate check**: the regular install flow and core portable bundles get the core app and image-to-3D inference running first. To generate 3D models from video, download the `cu128-rtx50-video-recon` bundle, or follow [Video Reconstruction Manual Environment Setup](#video-reconstruction-manual-environment-setup) to install the pinned Brush CLI, COLMAP and `ffmpeg/ffprobe`.
>
> 👉 Unverified platforms should theoretically work. Report issues on [GitHub Issues](https://github.com/lueluelue12138/sharp-gui/issues).

### Option 1: Windows Full Portable Bundle (Recommended for NVIDIA Users)

Windows RTX 50 / mainstream NVIDIA users can use the full portable bundle directly, without manually setting up Python, PyTorch, or the model cache. Pick the dedicated video reconstruction bundle when you need local video 3DGS reconstruction.

Permanent cloud-drive folder: [Open download folder](https://pan.quark.cn/s/94f4acaada40)

The same folder is kept up to date with the latest version. Pick the package for your GPU and use case:

- **RTX 50 series (core features)**: download the `cu128-rtx50` bundle
- **RTX 50 series (video 3DGS reconstruction)**: download the `cu128-rtx50-video-recon` bundle
- **Mainstream NVIDIA below RTX 50 (core features)**: download the `cu126-mainstream` bundle

Download the ZIP and matching `.sha256.txt`, verify SHA256 first, then extract and double-click `portable-run.bat`.

> 💡 Full portable bundles currently target NVIDIA GPUs only; there is no CPU-only portable bundle. The video reconstruction bundle currently targets the RTX 50 / CUDA 12.8 route and does not mean every NVIDIA GPU has been verified.
>
> 🔄 **Self-update bootstrap boundary**: the next full portable release containing the new updater is the first bootstrap bundle. Portable bundles at `v1.3.0` or earlier have neither a managed Git worktree nor bundled MinGit, so they require one final full-package download. Compatible code hotfixes can be applied incrementally after moving to the bootstrap bundle.

### Option 2: Install from Source (Recommended for macOS / Linux / Developers)

The source repo already includes the latest built frontend assets. For normal use, you do not need Node.js or a manual frontend build; run the install script to set up Python, then start the app.

```bash
# 1. Clone project
git clone https://github.com/lueluelue12138/sharp-gui.git
cd sharp-gui

# 2. Run install script (auto-clones ml-sharp and configures environment)
./install.sh      # Linux/macOS
# or
install.bat       # Windows

# 3. Start server
./run.sh          # Linux/macOS
# or
run.bat           # Windows
```

> 💡 Install Node.js and run `./build.sh` / `build.bat` only if you modify the frontend source and need to regenerate `frontend/dist/`.
>
> 💡 The install script auto-generates HTTPS certificates. HTTPS mode is recommended for full functionality.
>
> 🎥 If you need video reconstruction, finish the regular install first, then prepare the separate dependencies in [Video Reconstruction Manual Environment Setup](#video-reconstruction-manual-environment-setup).

### Option 3: Generic Release Package (No git clone)

The GitHub Release ZIP is a source snapshot with the built frontend already included. It is useful if you do not want to use `git clone`; functionally it is close to source install and still needs the install script to configure Python, dependencies, and models.

Download the latest version from [Releases](https://github.com/lueluelue12138/sharp-gui/releases):

```bash
# 1. Download and extract
unzip sharp-gui-vX.Y.Z.zip
cd sharp-gui

# 2. Run install script
./install.sh      # Linux/macOS
# or
install.bat       # Windows

# 3. Start server
./run.sh          # Linux/macOS
# or
run.bat           # Windows
```

> 💡 Want latest features? Download [Pre-release](https://github.com/lueluelue12138/sharp-gui/releases) versions (marked as `Pre-release`).
>
> 🎥 The regular Release ZIP flow covers the core app environment first; confirm video reconstruction dependencies separately via [Video Reconstruction Manual Environment Setup](#video-reconstruction-manual-environment-setup).

### What Does the Install Script Do?

The install script automatically handles all setup steps, no manual configuration needed:

- 🐍 **Detect/Install Python** - Auto-finds compatible version (3.10~3.13), auto-installs if missing (Windows)
- 📦 **Detect/Install Git** - Auto-installs if missing (Windows)
- 🎮 **Detect NVIDIA GPU** - Auto-installs the CUDA-enabled PyTorch that matches your driver (cu118 / cu126 / cu128)
- 🧩 **Install Dependencies** - Creates virtual environment, installs ml-sharp core and GUI deps
- 🎥 **Video reconstruction environment is prepared separately** - Brush CLI, COLMAP, and `ffmpeg/ffprobe` are not required for the regular install; follow [Video Reconstruction Manual Environment Setup](#video-reconstruction-manual-environment-setup) when you need video reconstruction
- 📥 **Pre-download Model** - Downloads the approximately 2.62 GiB inference model during install, avoiding a first-run wait
- 🔐 **Generate HTTPS Certificate** - Auto-generates self-signed certificate for secure LAN access

### Start Server

```bash
./run.sh          # Linux/macOS (React version)
./run.sh --legacy # Use original single-file version
# or
run.bat           # Windows
```

Access **https://127.0.0.1:5050 (recommended)** or **http://127.0.0.1:5050** 🎉

> 🩺 When reporting an issue, run in verbose mode: `./run_verbose.sh` / `run_verbose.bat`. It captures runtime info, command paths, PATH, and full exception traces into `sharp-gui-verbose.log`.

### Version and Updates

Open **Settings → Updates** to see the current version, choose a channel, check, and install. The app restarts automatically and restores the previous version if verification fails.

- **Stable (recommended)**: the highest formal `vX.Y.Z` tag in the repository.
- **Latest**: the newest commit on `main`. It receives hotfixes sooner but is less tested than Stable.

Portable bundles use their bundled Python and Git; clean source installations on `main` are supported too. Code updates preserve workspaces, models, configuration, and large Python/CUDA runtimes. If a target needs a different runtime, the app asks for a new complete bundle. Portable bundles at `v1.3.0` or earlier must first move to a complete bundle containing the new updater.

Use Settings if you do not need the command line. The scripts provide equivalent operations:

```bash
# Linux / macOS
./update.sh --channel stable --check
./update.sh --channel stable
```

```bat
:: Windows
update.bat --channel stable --check
update.bat --channel stable
```

Replace `stable` with `latest` to check or install Latest. Developers on another branch or with local code changes should keep using the normal Git workflow.

Developer and maintainer details are available in the Chinese guide: [Self-update development rules](../.agents/rules/self-update.md).

### Uninstall

Before removing an installation, check the workspace and configuration locations under **Settings → General**, back up the data you want to keep, and stop the service. If the workspace is inside the application directory, move or back it up first. Removing application files does not automatically remove an external workspace or the global user configuration.

Models, albums, caches and tool runtimes may be used by other installations; remove them only after confirming they are no longer needed. See [configuration and recovery](global-configuration.md) for storage locations.

## ⚙️ Configuration

### Keep Settings Across Complete Packages

Configuration now lives in the system user directory: `%LOCALAPPDATA%\SharpGUI\config.json` on Windows, `~/Library/Application Support/SharpGUI/config.json` on macOS, and `${XDG_CONFIG_HOME:-~/.config}/sharp-gui/config.json` on Linux. Another current-version package run by the same user reads it automatically and reuses the original workspace, models, and albums.

The first launch imports the **current installation's** old `config.json`. If you extracted a new package before registering the old configuration, choose the old package folder under **Settings → Configuration storage → Restore settings from an older version**. Confirmation backs up the current configuration and restarts the app. **Models remain in the original workspace: keep that data directory when replacing a package.** `SHARP_CONFIG_FILE` selects a completely isolated configuration; `SHARP_CONFIG_HOME` changes the global configuration directory. See the [configuration and recovery guide (Chinese)](global-configuration.md) for backup and failure handling.

New profiles use a stable workspace: the configuration directory's `workspace/` on Windows/macOS, or `${XDG_DATA_HOME:-~/.local/share}/sharp-gui/workspace` on Linux. Restoring replaces the whole configuration rather than merging it; active tasks, revision conflicts, or an unavailable workspace prevent confirmation. Browser-local viewer preferences and installation-level certificates/runtime dependencies are not migrated. Corrupt or previously initialized but missing configuration fails explicitly instead of resetting settings. Older app versions still use their package-local file; changes are not synchronized back to it.

### Custom Workspace

Configure via UI settings or edit the active `config.json` (find its location in Configuration storage; stop the service before manual edits):

```json
{
  "workspace_folder": "/path/to/workspace",
  "photo_gallery_roots_by_workspace": {
    "/path/to/workspace": [
      {
        "id": "my-album",
        "name": "Photos",
        "path": "/path/to/photos",
        "recursive": true,
        "enabled": true
      }
    ]
  }
}
```

The system auto-creates:

- `inputs/` - Uploaded images; `inputs/.thumbnails/` stores legacy/model thumbnail cache
- `outputs/` - Generated models and sidecar metadata (`.ply` / `.spz` / `.meta.json`)
- `model-assets/` - Controlled model asset file area: `imports/` stores imported models, `thumbnails/` stores cached covers
- `.model-asset-library/` - Model asset index and user-edited metadata (`index.json`)
- `.photo-gallery-cache/` - Local media gallery cache: `catalog.json`, `albums/`, `thumbnails/`, `video-posters/`, and temporary ZIP packages
- `.video-reconstruction/` - Video reconstruction runtime data: `jobs/` and `uploads/`

These workspace runtime folders are user data and are ignored by `.gitignore` by default; they should not be committed. After changing the workspace in Settings and letting the app restart, `inputs/`, `outputs/`, `model-assets/`, `.model-asset-library/`, `.photo-gallery-cache/`, and `.video-reconstruction/` all switch to the new workspace. Switching back to an old workspace restores that workspace's model assets, recent-model index, gallery cache, and task-related state.

Global configuration does not switch with the workspace. The old project-root `config.json` is only an initial import source. `cert.pem` / `key.pem`, `sharp-gui-verbose.log`, `venv/`, `.sharp-gui-tools/`, and `ml-sharp/` remain installation-level certificates, logs, or dependencies; sensitive files are never exposed through `/files/*`.

> 💡 Albums can be added from the UI and are remembered per workspace: `photo_gallery_roots_by_workspace` is keyed by the normalized workspace path, so switching workspaces shows each one's own albums and switching back restores them. When editing manually, use paths from the server machine. Windows, Linux, and macOS are supported; LAN clients browse folders on the host running Sharp GUI.
>
> ⚠️ Older versions stored albums in a top-level `photo_gallery_roots` array. On the first launch after upgrading, it is automatically migrated into the bucket for the current workspace — no manual action needed.

### Video Reconstruction Configuration

Settings stores default quality, actual VRAM budget and the intermediate-file preference. Videos use **Brush + COLMAP + ffmpeg/ffprobe**. Saved engine preferences migrate to Brush.

Diagnostics expose `required` (decoding) and `brush` (COLMAP and Brush). Startup warms the cache asynchronously; Refresh requests a new scan. Missing Brush does not trigger another trainer.

The preferred model format controls previews and downloads: SPZ is compact, while PLY preserves original data. Missing formats fall back to available assets.

### Video Reconstruction Manual Environment Setup

The current source route is **ffmpeg/ffprobe → native COLMAP → OOOBrush CLI 1.0.0**. Core bundles do not include video tools. Video tools do not require a separate Python training environment or CUDA Toolkit.

> Existing v2.0.0 video bundles use official Brush 0.3.0 (runtime revision 3). This engine change requires runtime revision 4 and cannot be installed as a code-only update. Until new complete bundles are published, source installations can install the pinned engine with the command below. Existing models require no migration.

#### 1. Install video tools

After installing the core app, run in the Windows project root:

```powershell
.\venv\Scripts\python.exe tools/install_video_reconstruction.py
```

The installer places native COLMAP in `.sharp-gui-tools/colmap/` and the hash-verified [OOOBrush ooo-v1.0.0](https://github.com/ooolabdev/OOOBrush/releases/tag/ooo-v1.0.0) in `.sharp-gui-tools/brush/ooo-v1.0.0/`. Engine versions use separate directories with complete provenance and licensing. FFmpeg and ffprobe are supplied by `install.bat` or the complete video bundle.

On Linux/macOS, install COLMAP and FFmpeg using your package manager, then run `python tools/install_brush.py`. A compatible GPU driver is needed. Use the Brush CLI, rather than merely opening its editor.

#### 2. Check the environment

Open Settings > Video Reconstruction and refresh, or request:

```powershell
curl.exe http://127.0.0.1:5050/api/video-reconstructions/status
```

| Group | Purpose |
| --- | --- |
| `required` | ffmpeg / ffprobe decoding |
| `brush` | Native COLMAP + pinned Brush CLI |

`summary.brush_available` reports complete-route readiness. High quality retains a 1920 long-edge cap / 15,000 iterations; Extreme retains 3840 / 30,000 on a 12 GB budget. Smaller inputs are never enlarged.

Intermediate files live in the workspace's `.video-reconstruction/jobs/`; PLY, SPZ and reports live in `outputs/`. Disabling intermediate retention removes the task folder while retaining models and reports. The legacy video environment is no longer used, but updates still protect old installation directories and existing models.

### Enable HTTPS (Recommended)

HTTPS enables **gyroscope on LAN devices** (browsers require secure context for sensor APIs).

The install script auto-generates certificates. For manual generation:

```bash
python tools/generate_cert.py
```

> 💡 **Windows Users**: Install [Git for Windows](https://git-scm.com/download/win) or OpenSSL first.

After generating, restart and access via `https://`:

| Mode      | Local                  | LAN               | Gyroscope     |
| --------- | ---------------------- | ----------------- | ------------- |
| **HTTPS** | https://127.0.0.1:5050 | https://[IP]:5050 | ✅ Available  |
| HTTP      | http://127.0.0.1:5050  | http://[IP]:5050  | ❌ Local only |

First HTTPS access shows certificate warning (self-signed), click "Continue" to proceed.

## 🔐 LAN Access Gate and Privacy Boundary

Sharp GUI ships an **optional** LAN access gate. On first startup—or whenever the local owner has not finished configuring it—the app shows a gentle reminder to set an access code; you can configure it later or stop showing the reminder. The gate is off by default; existing `config.json` files keep working unchanged.

### Permission Matrix

The table below shows the permission boundaries for each role:

| Action                                   | Public (locked remote) | Unlocked Remote (with access code) | Local Owner (localhost) |
| ---------------------------------------- | :--------------------: | :--------------------------------: | :---------------------: |
| Browse models / photos / thumbnails      | ❌ (when gate is on)   |                 ✅                 |           ✅            |
| Download originals / model files / HTML  | ❌ (when gate is on)   |                 ✅                 |           ✅            |
| Submit generation / photo-to-3D jobs     |          ❌            |  Only when "Remote Generation" is on |          ✅            |
| Modify settings / delete model / restart |          ❌            |                 ❌                 |           ✅            |
| Manage album folders / cancel tasks      |          ❌            |                 ❌                 |           ✅            |

### Key Behaviours

- **When the gate is on**, model lists, thumbnails, originals, photo albums, downloads, exports, and `/files/*` workspace resources require LAN devices to enter the access code first; after a successful unlock, the browser keeps an HttpOnly Cookie session.
- **When the gate is off**, devices on the same LAN that can reach the port may browse and download private content directly; deletion, settings, restart, folder management and other owner-only actions still require `localhost` / `127.0.0.1`.
- **Remote generation is off by default**: even with a valid access code, remote devices only get browse / preview / download / export permissions. To allow unlocked remote devices to submit generation jobs, enable Remote Generation in Settings > Access & security; turning the gate off also revokes remote generation permission.
- **Brute-force resistance**: failed logins back off per client, and the server validates the host allowlist plus real connection address — `X-Forwarded-For` and similar headers can never escalate to owner.
- **HTTPS vs gate**: HTTPS protects transport and browser sensor capabilities; the access code protects authorization. Enable both when sharing the port on your LAN.

### Privacy & Deployment Notes

- **Sensitive files stay private**: `/files/*` serves only `outputs/` models, legacy thumbnails, `model-assets/imports/` imported models, and `model-assets/thumbnails/` cover caches. `config.json` (session secret and access-code hash), `.model-asset-library/index.json`, `cert.pem`/`key.pem` (TLS private key), and `app.py` source **can never** be downloaded through that route, whether the gate is on or off.
- **LAN bind toggle is real**: Settings > Access & security lets you switch the listening bind. On listens on `0.0.0.0` (LAN sharing); off listens on `127.0.0.1` only (localhost-only, other devices cannot connect). A restart is required after changing it; `SHARP_BIND_HOST` can override.
- **Debug mode off by default**: the server runs without the framework debugger, so errors never leak stack traces and no interactive debugger is exposed. Set `SHARP_DEBUG=1` only for local troubleshooting, never when sharing on a LAN or the internet.
- **Reverse proxy caveat**: this service is designed to run directly on the local machine and normally needs no reverse proxy. If you do front it with a local proxy (nginx / frp, etc.), every request appears to come from `127.0.0.1`, so **every visitor is treated as owner**. To force the access code behind a proxy, set an access code first, then manually change `access_control.allow_localhost_bypass` to `false` in `config.json` (there is no Settings toggle for it). **Note: disabling the localhost bypass also drops local owner status, so self-update (checking / installing updates) becomes unavailable**; update via the `update.bat` / `update.sh` command line or a fresh complete package instead. The project never trusts spoofable forwarding headers such as `X-Forwarded-For`.
- **Public exposure warning**: this service is designed for LAN use. Before port-forwarding to the internet, enable the gate, set a strong access code, turn on HTTPS, and assess the risk yourself.
