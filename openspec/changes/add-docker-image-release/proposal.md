## Why

GitHub Issue #8 询问 Sharp GUI 是否会提供 Docker 镜像。增加 Docker 部署路径可以降低 Linux、NAS、家庭服务器用户的 Python/Node 环境配置成本，并为维护者提供一个可自动化、可复现的发布渠道，作为现有 Release ZIP 和 Windows 完整便携包的补充。

## What Changes

- 为 Sharp GUI 的 React + Flask + ml-sharp 运行时增加 Docker 镜像支持。
- 在版本 tag 发布时自动构建并推送容器镜像，首选 GitHub Container Registry (GHCR)。
- 按 CPU 与 NVIDIA CUDA 运行时拆分镜像标签，不承诺一个镜像覆盖所有 GPU 环境。
- 文档说明运行所需的 volume、端口、环境变量，以及 GPU 加速依赖的 NVIDIA Container Toolkit。
- 默认发布镜像支持联网首次运行，但不做完整离线包：Sharp 模型缓存保存在挂载的数据卷中，可首次使用时下载并复用。
- 增加 Docker 原生 owner 引导能力，使默认 bridge 网络下的宿主机浏览器也能完成门禁、设置、重启和本地相册目录等 owner-only 配置。
- 文档和界面说明 Docker 路径语义：宿主机目录必须先挂载到容器，再在 Sharp GUI 中配置容器内路径。
- 首版不包含 macOS/MPS 容器、Windows 容器、内置模型的 full/offline 镜像，以及 GPU CI 自动验证。

## Capabilities

### New Capabilities

- `docker-image-release`: 定义 Docker 镜像构建、发布、标签、运行时持久化，以及 CPU/NVIDIA CUDA 部署的用户使用说明。

### Modified Capabilities

- `docker-image-release`: 扩展 Docker 镜像运行时要求，增加 owner bootstrap 会话、Docker 路径配置和对应前端门禁/设置体验。

## Impact

- 发布自动化：`.github/workflows/` 新增或扩展 workflow，在 `v*` tag 上构建并发布容器镜像。
- 容器打包：仓库根目录新增 Docker 相关文件，例如 `Dockerfile`、`.dockerignore` 和可选 Compose 示例。
- 运行时配置：启动路径需要支持容器友好的 `config.json`、workspace 数据、模型缓存和 `sharp` CLI 路径，同时不破坏现有脚本安装方式。
- 后端安全：需要增加明确的 Docker owner token 验证和 owner session，不依赖 Docker 网桥 IP、host network 或任何转发头。
- 前端体验：门禁页和设置页需要提供符合现有 Apple 玻璃态风格的 Docker 管理员验证入口，并保持中英文 i18n 同步。
- 文档：`README.md`、`README.en.md` 和 release note 需要补充 Docker/GHCR 使用方式、GPU 前置条件和范围边界。
- 依赖与外部系统：发布镜像依赖 Python、ml-sharp、PyTorch CPU/CUDA 构建、GHCR，以及宿主机侧 NVIDIA Container Toolkit。
