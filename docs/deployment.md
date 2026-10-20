# 安装、配置与局域网访问

[English](deployment.en.md) · [返回 README](../README.md) · [使用指南](usage.md)

这里集中保留完整安装方式、环境准备、配置和访问边界；首次上手可先看 [README 快速开始](../README.md#-快速开始)。

## 🚀 快速开始

### 系统要求

| 平台                        | 推理后端  | 状态      |
| --------------------------- | --------- | --------- |
| **macOS Apple Silicon**     | ✅ MPS    | ✅ 已验证 |
| **Windows x86_64**          | ✅ CPU    | ✅ 已验证 |
| **Windows x86_64 + NVIDIA** | ✅ CUDA   | ✅ 已验证 |
| **Linux x86_64**            | ✅ CPU    | ✅ 已验证 |
| **Linux x86_64 + NVIDIA**   | ✅ CUDA   | ❓ 未验证 |
| **macOS Intel**             | ✅ CPU    | ❓ 未验证 |

> 🎥 **视频推理当前验证平台**：视频 3DGS 重建目前仅在 **Windows + NVIDIA RTX 5070 Ti Laptop GPU（12GB 显存）** 上完成端到端验证。其他 Windows NVIDIA 显卡可作为兼容方向尝试，但 Linux、macOS、CPU/MPS 视频重建暂未验证。
>
> 🚀 **推荐使用 NVIDIA GPU**：3D 高斯溅射推理是计算密集型任务，CUDA 加速通常比纯 CPU 快 **数倍到十数倍**，体验差距明显。
>
> 💡 **没有 GPU 也能跑**：纯 CPU 环境下推理也能完成，只是单张图片生成耗时更长；Apple Silicon 用户可享受 MPS 后端的近 GPU 体验。
>
> 🛠️ **零手动配置**：有 NVIDIA GPU 时，安装脚本会自动检测驱动并匹配对应的 PyTorch CUDA 版本（cu118 / cu126 / cu128）。
>
> 🎥 **视频重建环境需单独确认**：常规安装和核心便携包会先保证主程序和图片 3D 推理可用；如果要从视频生成 3D 模型，请下载 `cu128-rtx50-video-recon` 包，或按 [视频重建环境手动搭建指南](#视频重建环境手动搭建指南) 安装固定版本 Brush CLI、COLMAP 和 `ffmpeg/ffprobe`。
>
> 👉 未验证平台理论上可正常工作，如遇问题欢迎在 [Issues](https://github.com/lueluelue12138/sharp-gui/issues) 反馈。

### 方式一：Windows 完整便携包 (推荐 NVIDIA 用户)

Windows RTX 50 / 主流 NVIDIA 用户可直接下载完整便携包，无需手动配置 Python、PyTorch 或模型缓存。需要视频重建时，请选择专门的视频重建完整包。

固定网盘入口：[点击打开网盘文件夹](https://pan.quark.cn/s/94f4acaada40)

网盘文件夹会持续更新到最新版本，请按显卡和用途选择：

- **RTX 50 系列（核心功能）**：下载 `cu128-rtx50` 包
- **RTX 50 系列（视频 3DGS 重建）**：下载 `cu128-rtx50-video-recon` 包
- **RTX 50 以下主流 NVIDIA（核心功能）**：下载 `cu126-mainstream` 包

下载 ZIP 和同名 `.sha256.txt` 后先校验 SHA256，解压后双击 `portable-run.bat` 启动。

> 💡 完整便携包目前面向 NVIDIA GPU，不提供纯 CPU 包；视频重建完整包当前只按 RTX 50 / CUDA 12.8 路线发布，不代表所有 NVIDIA GPU 都已完成验证。
>
> 🔄 **自更新 bootstrap 边界**：包含新更新系统的下一版完整便携包是首个 bootstrap 包。`v1.3.0` 及更早便携包没有受管 Git 工作树和内置 MinGit，必须最后下载一次新的完整包；从 bootstrap 包开始，兼容的代码 hotfix 才能直接增量更新。

### 方式二：从源码安装 (推荐 macOS / Linux / 开发者)

源码仓库已包含最新前端构建产物，普通使用不需要安装 Node.js 或手动构建前端；运行安装脚本配置 Python 环境后即可启动。

```bash
# 1. 克隆项目
git clone https://github.com/lueluelue12138/sharp-gui.git
cd sharp-gui

# 2. 运行安装脚本 (自动拉取 ml-sharp 并配置环境)
./install.sh      # Linux/macOS
# 或
install.bat       # Windows

# 3. 启动服务
./run.sh          # Linux/macOS
# 或
run.bat           # Windows
```

> 💡 只有需要修改前端源码时，才需要安装 Node.js 并运行 `./build.sh` / `build.bat` 重新生成 `frontend/dist/`。
>
> 💡 安装脚本会自动生成 HTTPS 证书，建议使用 HTTPS 模式以获得完整功能。
>
> 🎥 需要视频重建功能时，先完成常规安装，再参考 [视频重建环境手动搭建指南](#视频重建环境手动搭建指南) 准备独立依赖。

### 方式三：通用 Release 包 (免 git clone)

GitHub Release ZIP 是源码仓库的发布快照，也包含已构建好的前端。它适合不想使用 `git clone` 的用户；功能和源码安装方式基本一致，仍需要运行安装脚本配置 Python 环境、下载依赖和模型。

从 [Releases](https://github.com/lueluelue12138/sharp-gui/releases) 页面下载最新版本：

```bash
# 1. 下载并解压
unzip sharp-gui-vX.Y.Z.zip
cd sharp-gui

# 2. 运行安装脚本
./install.sh      # Linux/macOS
# 或
install.bat       # Windows

# 3. 启动服务
./run.sh          # Linux/macOS
# 或
run.bat           # Windows
```

> 💡 想尝鲜最新功能？可下载 [Pre-release](https://github.com/lueluelue12138/sharp-gui/releases) 版本（标记为 `Pre-release` 的版本）。
>
> 🎥 Release ZIP 的常规安装同样先覆盖主程序环境；视频重建依赖请参考 [视频重建环境手动搭建指南](#视频重建环境手动搭建指南) 单独确认。

### 安装脚本做了什么？

安装脚本会自动完成以下步骤，无需手动配置：

- 🐍 **检测/安装 Python** - 自动查找兼容版本 (3.10~3.13)，缺失时自动安装 (Windows)
- 📦 **检测/安装 Git** - 缺失时自动安装 (Windows)
- 🎮 **检测 NVIDIA GPU** - 有 GPU 时自动安装匹配驱动的 CUDA 版 PyTorch（cu118 / cu126 / cu128）
- 🧩 **安装依赖** - 创建虚拟环境，安装 ml-sharp 核心和 GUI 依赖
- 🎥 **视频重建环境需单独准备** - Brush CLI、COLMAP 和 `ffmpeg/ffprobe` 不作为常规安装的必需项；需要视频重建时请参考 [视频重建环境手动搭建指南](#视频重建环境手动搭建指南)
- 📥 **预下载模型** - 安装阶段即下载约 2.62 GiB 的推理模型，避免首次运行等待
- 🔐 **生成 HTTPS 证书** - 自动生成自签名证书，支持局域网安全访问

### 启动服务

```bash
./run.sh          # Linux/macOS (React 版本)
./run.sh --legacy # 使用原始单文件版本
# 或
run.bat           # Windows
```

访问 **https://127.0.0.1:5050 (推荐)** 或 **http://127.0.0.1:5050** 即可使用 🎉

> 🩺 反馈问题时可使用 verbose 模式：`./run_verbose.sh` / `run_verbose.bat`，会同步记录运行环境、命令路径、PATH 与完整异常栈到 `sharp-gui-verbose.log`。

### 版本与更新

在 **设置 → 更新中心**，即可查看当前版本、选择通道、检查并安装更新。更新时应用会自动重启；如果新版本验证失败，会自动恢复上一版本。

- **Stable（推荐）**：仓库中版本号最高的正式 `vX.Y.Z` 标签。
- **Latest**：`main` 分支的最新提交，可更早获得 hotfix，但测试程度低于 Stable。

便携包会使用包内 Python 和 Git；干净且位于 `main` 的源码安装也可使用。代码更新会保留 workspace、模型、配置和 Python/CUDA 等大型运行环境；如目标版本需要更换运行环境，应用会提示下载新的完整便携包。`v1.3.0` 及更早便携包需要先升级到包含新更新系统的完整包。

不熟悉命令行时直接使用 Settings 即可；脚本提供等价操作：

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

将 `stable` 换成 `latest` 即可检查或安装 Latest。开发分支或存在本地代码修改时，请继续使用正常 Git 工作流。

开发与维护细节见中文文档：[自更新系统开发规范](../.agents/rules/self-update.md)。

### 卸载

先在 **设置 → 常规** 中确认工作区和配置位置，备份需要保留的数据，再停止服务并删除应用目录。如果工作区位于应用目录内，应先移出或备份。删除应用文件不会自动清理独立工作区或用户目录中的全局配置。

模型、相册、缓存和工具运行环境可能仍被另一套安装使用，确认不再需要后再清理。存储位置见[配置存储与恢复](global-configuration.md)。

## ⚙️ 配置选项

### 换包保留配置

配置默认保存在系统用户目录：Windows 为 `%LOCALAPPDATA%\SharpGUI\config.json`，macOS 为 `~/Library/Application Support/SharpGUI/config.json`，Linux 为 `${XDG_CONFIG_HOME:-~/.config}/sharp-gui/config.json`。同一用户运行另一套新版完整包时会自动读取它，继续使用原工作区、模型及相册。

首次运行会导入**当前安装目录**的旧 `config.json`；如果直接在全新目录换包、旧配置尚未登记，请在「设置 → 配置存储 → 从旧版本恢复配置」选择旧包文件夹。确认前备份当前配置，恢复后自动重启。**模型仍在原工作区，不能因换包而删除旧数据目录。** `SHARP_CONFIG_FILE` 可指定完全独立的配置，`SHARP_CONFIG_HOME` 可指定全局配置目录。详见[全局配置与恢复说明](global-configuration.md)。

### 自定义工作目录

可通过界面设置或编辑当前活动的 `config.json`（实际位置见「配置存储」，手动编辑前关闭服务）:

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

系统会自动在工作目录下创建：

- `inputs/` - 上传图片；`inputs/.thumbnails/` 保存历史/模型缩略图缓存
- `outputs/` - 生成模型和 sidecar 元数据（`.ply` / `.spz` / `.meta.json`）
- `model-assets/` - 模型资产受控文件区：`imports/` 保存导入模型，`thumbnails/` 保存封面缓存
- `.model-asset-library/` - 模型资产索引与用户编辑信息（`index.json`）
- `.photo-gallery-cache/` - 本地媒体图库缓存：`catalog.json`、`albums/`、`thumbnails/`、`video-posters/` 和临时打包 ZIP
- `.video-reconstruction/` - 视频重建运行时数据：`jobs/` 和 `uploads/`

这些工作区运行时目录属于用户数据，默认已在 `.gitignore` 中排除，不应提交到仓库。切换 Settings 中的工作目录并自动重启后，`inputs/`、`outputs/`、`model-assets/`、`.model-asset-library/`、`.photo-gallery-cache/` 和 `.video-reconstruction/` 都会切到新工作目录；切回旧工作目录即可找回对应的模型资产、近期模型索引、相册缓存和任务相关状态。

全局配置不随 workspace 切换。项目根目录下的旧 `config.json` 仅作为首次导入来源；`cert.pem` / `key.pem`、`sharp-gui-verbose.log` 以及 `venv/`、`.sharp-gui-tools/`、`ml-sharp/` 仍是安装级证书、日志或依赖目录；其中敏感文件不会通过 `/files/*` 暴露。

> 💡 相册可通过界面添加，并按工作目录分别记忆：`photo_gallery_roots_by_workspace` 以归一化后的工作目录路径为键，切换工作目录时各自展示对应相册，切回原目录即可恢复。手动编辑时请按部署端系统填写路径。Windows、Linux、macOS 均可使用，局域网设备访问时读取的是服务器所在机器的目录。
>
> ⚠️ 旧版本使用顶层 `photo_gallery_roots` 数组保存相册，升级后首次启动会自动迁移到当前工作目录对应的分桶，无需手动处理。

### 视频重建配置

Settings 中的「视频重建」区域保存默认质量、实际显存预算和中间文件保留选项。视频统一使用 **Brush + COLMAP + ffmpeg/ffprobe**。旧配置的引擎选择自动迁移为 Brush。

诊断显示 `required`（视频解码）和 `brush`（COLMAP、Brush）两组。后端启动后异步预热诊断，弹窗复用缓存，Settings 中点击刷新可重新检测；缺少 Brush 时不会切换到其它训练路线。

「默认模型格式」控制模型资产库、近期模型、下载与预览的格式优先级：SPZ 适合紧凑传输，PLY 保留原始数据；首选格式缺失时回退至资产可用格式。

### 视频重建环境手动搭建指南

路线为 **ffmpeg/ffprobe → 原生 COLMAP → 官方 Brush CLI v0.3.0**。RTX 50 用户可直接下载 `cu128-rtx50-video-recon` 完整便携包；核心包不包含视频工具。视频工具不需要独立 Python 训练环境或 CUDA Toolkit。

#### 1. 安装视频工具

先完成主程序安装，再在 Windows 项目根目录运行：

```powershell
.\venv\Scripts\python.exe tools/install_video_reconstruction.py
```

安装器把原生 COLMAP 放在 `.sharp-gui-tools/colmap/`，把经哈希验证的官方 [Brush v0.3.0](https://github.com/ArthurBrussee/brush/releases/tag/v0.3.0) 放在 `.sharp-gui-tools/brush/v0.3.0/`。旧安装会只迁移已有原生 COLMAP 的程序及 DLL，不复制旧虚拟环境。FFmpeg 与 ffprobe 由 `install.bat` 安装或完整视频包提供。

Linux/macOS 用户通过系统包管理器安装 COLMAP、FFmpeg，再运行 `python tools/install_brush.py`。需要兼容 GPU 驱动；请使用 Brush CLI，而非仅打开 Brush 编辑器。

#### 2. 检查环境

启动后打开 Settings > 视频重建并刷新，或读取：

```powershell
curl.exe http://127.0.0.1:5050/api/video-reconstructions/status
```

| 分组 | 作用 |
| --- | --- |
| `required` | ffmpeg / ffprobe 视频解码 |
| `brush` | 原生 COLMAP + 固定版本 Brush CLI |

`summary.brush_available` 为完整路线可运行状态。高质量档保持 1920 长边 / 15,000 次迭代，极致档为 3840 长边 / 30,000 次迭代（12 GB 预算）；输入尺寸较小不会放大。

重建运行文件位于当前 workspace 的 `.video-reconstruction/jobs/`，最终 PLY、SPZ 和报告位于 `outputs/`。关闭保留中间文件后会清理任务目录，模型及报告保留。旧视频虚拟环境不再用于重建，更新仍保护旧安装目录与已有模型。

### 启用 HTTPS (推荐)

启用 HTTPS 后可支持**局域网设备的陀螺仪功能**（浏览器要求安全上下文才能访问传感器 API）。

安装脚本会自动尝试生成证书。如需手动生成：

```bash
python tools/generate_cert.py
```

> 💡 **Windows 用户**: 需要先安装 [Git for Windows](https://git-scm.com/download/win) 或 OpenSSL。

生成成功后重启服务，使用 `https://` 访问：

| 模式      | 本机                   | 局域网            | 陀螺仪    |
| --------- | ---------------------- | ----------------- | --------- |
| **HTTPS** | https://127.0.0.1:5050 | https://[IP]:5050 | ✅ 可用   |
| HTTP      | http://127.0.0.1:5050  | http://[IP]:5050  | ❌ 仅本机 |

首次访问 HTTPS 时浏览器会提示证书警告（因为是自签名证书），选择「继续访问」即可。

## 🔐 局域网门禁与隐私边界

Sharp GUI 提供**可选**的局域网门禁。首次启动或本机尚未完整配置门禁时，会提示 owner 设置访问码；用户也可以稍后设置或选择不再提示。门禁默认关闭，旧 `config.json` 无需迁移。

### 权限分级一览

下表展示三类访问者在不同操作上的权限边界：

| 操作                                | 公开访问（未解锁远程） | 已解锁远程（输入访问码后） | 本机 Owner（localhost） |
| ----------------------------------- | :--------------------: | :------------------------: | :---------------------: |
| 浏览模型 / 照片 / 缩略图            |    ❌（门禁开启时）    |             ✅             |           ✅            |
| 下载原图 / 模型文件 / 导出 HTML     |    ❌（门禁开启时）    |             ✅             |           ✅            |
| 提交生成 / 照片转 3D 任务           |           ❌           |  仅在显式开启「远程生成」  |           ✅            |
| 修改设置 / 删除模型 / 重启服务      |           ❌           |             ❌             |           ✅            |
| 添加/删除相册目录 / 取消任务        |           ❌           |             ❌             |           ✅            |

### 关键行为

- **门禁开启时**，模型列表、缩略图、原图、照片相册、下载、导出和 `/files/*` 工作区资源都需要远程设备先输入访问码；解锁后浏览器会保存 HttpOnly Cookie 会话。
- **门禁关闭时**，同一局域网内能访问端口的设备可直接浏览和下载私有内容；删除、设置、重启、目录管理等 owner-only 操作仍仅限 `localhost` / `127.0.0.1`。
- **远程生成默认关闭**：远程设备即使输入了访问码，也默认只有浏览、预览、下载和导出权限。如需允许已解锁的远程设备提交生成任务，可在 设置「访问与安全」中开启"远程生成"；关闭门禁会同时收回远程生成权限。
- **抗暴力猜测**：登录失败按客户端递增延迟，并校验 Host 允许列表与真实连接地址，避免 DNS rebinding 或伪造转发头绕过 owner 判断。
- **HTTPS 与门禁分工**：HTTPS 负责传输加密和浏览器传感器能力，访问码负责访问资格；在局域网共享端口时建议两者都启用。

### 隐私与部署须知

- **敏感文件不外泄**：`/files/*` 仅服务 `outputs/` 模型、历史缩略图、`model-assets/imports/` 导入模型和 `model-assets/thumbnails/` 封面缓存；`config.json`（含会话密钥与访问码哈希）、`.model-asset-library/index.json`、`cert.pem`/`key.pem`（TLS 证书私钥）、`app.py` 源码等敏感文件**在门禁开启或关闭时都无法**通过该路由下载。
- **局域网绑定开关真实生效**：设置「访问与安全」中可切换监听绑定。开启时服务监听 `0.0.0.0`（局域网共享）；关闭后仅监听 `127.0.0.1`（仅本机，其它设备无法连接）。修改后需重启服务生效，可用环境变量 `SHARP_BIND_HOST` 覆盖。
- **调试模式默认关闭**：服务默认以非调试模式运行，异常不会向客户端返回堆栈，也不暴露交互式调试器。仅本机排障时可设 `SHARP_DEBUG=1` 临时开启，切勿在局域网/公网共享时开启。
- **反向代理注意**：本服务面向本机直接运行设计，通常不需要反向代理。若确实在本机前置反向代理（nginx / frp 等），所有请求的来源地址会变成 `127.0.0.1`，导致**每个访问者都被判为 owner**。如需在反代后强制访问码，可先设置访问码，再手动将 `config.json` 中的 `access_control.allow_localhost_bypass` 改为 `false`（该项目前没有设置界面开关）。**注意：关闭本机免登录会同时取消本机 owner 身份，导致自更新（检查 / 安装更新）不可用**，届时更新只能通过命令行 `update.bat` / `update.sh` 或安装新的完整包进行。本项目不信任 `X-Forwarded-For` 等可被伪造的转发头。
- **公网暴露提醒**：本服务面向局域网设计。如需端口转发到公网，请务必先开启门禁、设置强访问码并启用 HTTPS，自行评估风险。
