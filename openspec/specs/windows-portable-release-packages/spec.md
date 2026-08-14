# windows-portable-release-packages Specification

## Purpose

定义 Sharp GUI 在 Windows x64 NVIDIA GPU 环境下的完整便携 ZIP 发布能力，包括本地一键打包、硬件分包、包内运行时路径、校验文件、缓存策略，以及 GitHub Release 通过网盘链接分发大包的说明要求。

## Requirements

### Requirement: Windows Release 必须提供按 GPU 目标区分的完整便携 ZIP 包

Windows Release MUST 提供 Windows x64 GPU 完整便携 ZIP 包的外部下载链接，并按支持的 NVIDIA 运行时目标拆分；便携包路径不得要求普通用户再运行在线依赖安装脚本。Release MUST 保持核心包和视频重建增强包的用途边界清晰。

#### Scenario: RTX 50 用户下载匹配核心包

- **WHEN** 用户使用 RTX 50 系列 GPU 且只需要核心图片生成和模型浏览能力
- **THEN** Release 必须链接到 `cu128-rtx50` 完整便携 ZIP
- **AND** 包元数据必须声明该包面向 RTX 50 / CUDA 12.8 兼容驱动
- **AND** 该核心包 MUST NOT 强制包含视频重建完整运行时

#### Scenario: RTX 50 视频重建用户下载增强包

- **WHEN** 用户使用 RTX 50 系列 GPU 且需要本地视频 3DGS 重建能力
- **THEN** Release 必须在该包可用时链接到 `cu128-rtx50-video-recon` 完整便携 ZIP
- **AND** 包元数据必须声明该包面向 RTX 50 / CUDA 12.8 视频重建路线
- **AND** Release 说明 MUST 将该包标记为包含 Nerfstudio/Splatfacto、COLMAP 和 ffmpeg/ffprobe 的视频重建增强包

#### Scenario: 非 RTX 50 NVIDIA 用户下载主流核心包

- **WHEN** 用户使用受支持的非 RTX 50 NVIDIA GPU
- **THEN** Release 必须在该包可用时链接到 `cu126-mainstream` 完整便携 ZIP
- **AND** 包元数据必须声明该包要求的最低驱动 CUDA 能力
- **AND** Release MUST NOT 暗示该包已经包含已验证的视频重建完整运行时

#### Scenario: 不提供纯 CPU 包

- **WHEN** Windows 完整便携包版本列出下载说明
- **THEN** Release 不得把纯 CPU 包作为受支持下载选项展示

### Requirement: 本地打包脚本必须生成完整 ZIP 与校验文件

Windows 便携包流程 MUST 包含本地一键打包脚本，用于生成完整 ZIP、包元数据和 SHA256 校验文件。打包脚本 MUST 支持同时生成核心包和可选的视频重建增强包。

#### Scenario: 维护者在本地构建核心便携包

- **WHEN** 维护者在已验证的 Windows GPU 环境中运行本地打包脚本
- **THEN** 脚本必须构建或验证 React 前端
- **AND** 脚本必须把应用、Python 运行时、Python 依赖、所选前端依赖、`ml-sharp` 源码、模型缓存、便携启动入口和包元数据复制到 staging 目录
- **AND** 脚本必须产出用于外部分发的 `cu128-rtx50` 和 `cu126-mainstream` 完整 ZIP，除非维护者显式跳过对应目标

#### Scenario: 维护者在本地构建视频重建增强包

- **WHEN** 维护者运行一键打包脚本且未跳过视频重建包
- **THEN** 脚本必须生成 `cu128-rtx50-video-recon` 完整 ZIP
- **AND** 该 ZIP 必须包含核心 `cu128-rtx50` 包的运行能力
- **AND** 该 ZIP 必须包含可迁移的视频重建运行时

#### Scenario: 生成包校验文件

- **WHEN** 完整 ZIP 创建完成
- **THEN** 打包脚本必须为每个 ZIP 生成 `.sha256.txt` 文件
- **AND** 该校验值必须适合发布到 GitHub Release 正文和外部网盘说明页

#### Scenario: 打包脚本默认保留有用缓存

- **WHEN** 维护者使用默认选项运行一键发布打包脚本
- **THEN** 脚本必须保留 `.portable-venvs` 等可复用打包缓存
- **AND** 脚本必须保留输出目录中的历史 ZIP 产物
- **AND** 脚本必须在完成后打印缓存位置和手动清理说明

### Requirement: 便携启动器必须使用包内运行时路径

Windows 便携启动器 MUST 使用包内运行时路径启动 Sharp GUI，使启动过程不依赖系统级 Python、Node、Git、pip 网络访问或 CUDA Toolkit。包含视频重建运行时的包 MUST 在启动时优先接入包内视频重建命令路径。

#### Scenario: 用户启动已解压的核心便携包

- **WHEN** 用户在解压后的核心包目录运行 `portable-run.bat`
- **THEN** 启动器必须设置包内 `PATH`、`TORCH_HOME`、`PYTHONUTF8`、`PYTHONIOENCODING` 和 `SHARP_FRONTEND_MODE`
- **AND** 启动器必须使用包内 Python 运行时启动 `app.py`

#### Scenario: 用户启动已解压的视频重建增强包

- **WHEN** 用户在解压后的 `cu128-rtx50-video-recon` 包目录运行 `portable-run.bat`
- **THEN** 启动器必须优先把包内 `.video-reconstruction-env\Scripts`、`.video-reconstruction-env\colmap\bin` 和包内 `ffmpeg/ffprobe` 目录加入 `PATH`
- **AND** 后端依赖诊断 SHALL 能发现包内 `ns-process-data`、`ns-train`、`ns-export`、`colmap`、`ffmpeg` 和 `ffprobe`

#### Scenario: 必须提供包内 Sharp CLI

- **WHEN** 后端调用 `sharp` 命令执行推理
- **THEN** 便携包必须提供包内 `sharp.cmd` 入口
- **AND** 该入口必须通过包内 Python 运行时调用 `sharp.cli:main_cli`

### Requirement: 视频重建增强包必须包含可迁移运行时

Windows 视频重建增强便携包 MUST 包含以包目录相对路径工作的 Nerfstudio/Splatfacto、gsplat、COLMAP 和 ffmpeg/ffprobe 运行时，并避免要求目标机器复用打包机路径。

#### Scenario: 包目录移动到另一个位置

- **WHEN** 用户把解压后的 `cu128-rtx50-video-recon` 包目录移动到另一个 Windows 路径或另一个 Windows 用户目录
- **THEN** `ns-process-data`、`ns-train`、`ns-export`、`colmap`、`ffmpeg` 和 `ffprobe` MUST 仍通过包内相对路径解析
- **AND** 启动和诊断 MUST NOT 要求 `C:\workspace\sharp-gui` 或打包机用户目录存在

#### Scenario: 视频重建命令快速校验

- **WHEN** 打包流程校验 `cu128-rtx50-video-recon` 包
- **THEN** 校验 MUST 确认包内 CUDA PyTorch 可导入并能执行基础 CUDA kernel
- **AND** 校验 MUST 确认 `ns-process-data --help`、`ns-train --help`、`ns-export --help`、`colmap -h`、`ffmpeg -version` 和 `ffprobe -version` 可执行

#### Scenario: 目标机器缺少系统级视频工具

- **WHEN** 目标机器 PATH 中没有系统级 Nerfstudio、COLMAP 或 ffmpeg
- **THEN** 视频重建增强包 MUST 仍能通过包内路径通过依赖诊断
- **AND** 系统 MUST NOT 要求用户运行在线安装脚本后才获得视频重建命令

### Requirement: 便携运行时必须把模型与缓存数据放在包工作区内

Windows 便携运行时 MUST 使用包内路径保存模型文件和运行缓存，使启动过程不依赖用户 home 目录中的缓存。

#### Scenario: 模型已包含在包资产中

- **WHEN** 完整 ZIP 解压后便携运行时启动
- **THEN** Sharp GUI 必须使用 `.cache\torch\hub\checkpoints` 下的包内模型文件
- **AND** 正常启动时不得尝试重新下载 Sharp 模型

#### Scenario: 用户从另一个 Windows 账号运行

- **WHEN** 包目录被移动到另一个 Windows 用户配置目录
- **THEN** 启动器必须按包目录相对路径解析模型和缓存路径
- **AND** 启动不得要求原始打包机器或原始 Windows 用户配置目录中的文件

### Requirement: GitHub Release 必须用中文说明链接到外部完整 ZIP 包

GitHub Release MUST 提供中文说明和外部下载链接，引导用户下载完整 Windows 便携 ZIP 包，而不是要求 GitHub 直接托管大型 ZIP 文件。Release 说明 MUST 明确区分核心包和视频重建增强包。

#### Scenario: 外部包发布

- **WHEN** Windows 便携包发布
- **THEN** 维护者必须把完整 ZIP 和匹配的 SHA256 文件上传到外部存储服务
- **AND** GitHub Release 必须链接到这些外部文件

#### Scenario: Release Note 解释下载矩阵

- **WHEN** GitHub Release 创建
- **THEN** Release 正文必须用中文说明 RTX 50 核心用户、RTX 50 视频重建用户和非 RTX 50 NVIDIA 核心用户分别应该下载哪个完整 ZIP
- **AND** Release 正文必须包含 SHA256 值或 SHA256 文件链接
- **AND** Release 正文必须说明当前不提供纯 CPU 完整便携包
- **AND** Release 正文 MUST NOT 把视频重建增强包描述为已覆盖所有 NVIDIA GPU

### Requirement: Windows portable packages MUST include a self-contained code update baseline

Every Windows portable package produced after the self-update bootstrap release MUST contain a verified non-interactive Git runtime, an exact managed Sharp GUI source revision, and sufficient package metadata to check, apply, verify, and roll back compatible code updates without system Python, system Git, Node, npm, or a complete package redownload.

#### Scenario: Maintainer builds a portable package
- **WHEN** the Windows portable builder prepares a package staging tree
- **THEN** it MUST acquire a pinned official standard x64 MinGit artifact and verify its configured SHA256 before extraction
- **AND** the package MUST preserve the distribution's included license and notice files

#### Scenario: Package records update provenance
- **WHEN** portable package metadata is written
- **THEN** it SHALL include the exact Sharp GUI source commit, formal release baseline, canonical repository, package target, portable runtime revision, update protocol revision, bundled Git version, bundled Git digest, and relative executable location
- **AND** it MUST NOT contain maintainer credentials or machine-specific absolute paths

#### Scenario: Package seeds managed source
- **WHEN** the package staging tree is finalized
- **THEN** tracked application files and the Git index SHALL match the recorded source commit cleanly
- **AND** package runtime/user paths SHALL remain ignored or untracked so future checkout cannot delete them

#### Scenario: Portable update tools are invoked
- **WHEN** the UI or `update.bat` checks or applies an update
- **THEN** the package SHALL call its own embedded Python and MinGit by package-relative location
- **AND** the operation MUST NOT depend on similarly named executables on the user's PATH

### Requirement: Portable package validation MUST cover self-update isolation

The Windows portable build verification SHALL prove that the bundled updater is executable without system Git/Python, that the managed baseline is clean, and that a compatible commit update preserves package/runtime/workspace state while converging tracked files exactly.

#### Scenario: Package plan is inspected
- **WHEN** the maintainer runs the one-click portable release plan
- **THEN** the plan SHALL report the configured MinGit version, source asset, expected SHA256, source commit, and runtime compatibility revision for every non-skipped target

#### Scenario: Clean extracted package checks update tools
- **WHEN** a package is extracted into a clean test directory with system Git and Python excluded from PATH
- **THEN** bundled Git SHALL report the pinned version and the update CLI SHALL report the package's current version/revision
- **AND** the managed tracked worktree SHALL be clean before update

#### Scenario: Compatible test commit is applied
- **WHEN** verification applies a compatible target containing tracked additions, modifications, deletions, and renames
- **THEN** the resulting managed files SHALL exactly match the target commit
- **AND** markers in config, workspace data, model/runtime caches, embedded Python, optional reconstruction environment, package metadata, and bundled Git SHALL remain present

#### Scenario: Target runtime revision is incompatible
- **WHEN** the verification target declares a different portable runtime revision
- **THEN** the updater MUST refuse before changing the managed commit
- **AND** the clean package SHALL remain launchable at its previous revision

### Requirement: Portable release documentation MUST disclose updater tooling and compatibility boundaries

Portable package notes and bilingual project documentation SHALL identify the full-package bootstrap boundary, Stable and Latest channel meanings, bundled MinGit version/source/license location, code-only compatibility gate, preserved data/runtime paths, automatic failure recovery, and conditions that require a new complete package.

#### Scenario: User reads portable package notes
- **WHEN** a user considers applying a Latest commit update
- **THEN** the notes SHALL explain that latest is less tested than Stable and only compatible code changes are installed
- **AND** they SHALL explain that Python/CUDA/video-runtime revision changes require a new complete package

#### Scenario: Maintainer publishes a portable release
- **WHEN** a bootstrap-or-later portable ZIP is released through external storage
- **THEN** its release documentation SHALL record the bundled Git provenance and preserve the existing package ZIP SHA256 guidance
