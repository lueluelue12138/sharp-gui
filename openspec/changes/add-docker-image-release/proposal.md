## Why

GitHub Issue #8 询问 Sharp GUI 是否会提供 Docker 镜像。增加 Docker 部署路径可以降低 Linux、NAS、家庭服务器用户的 Python/Node 环境配置成本，并为维护者提供一个可自动化、可复现的发布渠道，作为现有 Release ZIP 和 Windows 完整便携包的补充。

## What Changes

- 为 Sharp GUI 的 React + Flask + ml-sharp 运行时增加 Docker 镜像支持。
- 在版本 tag 发布时自动构建并推送容器镜像，首选 GitHub Container Registry (GHCR)。
- 按 CPU 与 NVIDIA CUDA 运行时拆分镜像标签，不承诺一个镜像覆盖所有 GPU 环境。
- 文档说明运行所需的 volume、端口、环境变量，以及 GPU 加速依赖的 NVIDIA Container Toolkit。
- 默认发布镜像支持联网首次运行，但不做完整离线包：Sharp 模型缓存保存在挂载的数据卷中，可首次使用时下载并复用。
- 首版不包含 macOS/MPS 容器、Windows 容器、内置模型的 full/offline 镜像，以及 GPU CI 自动验证。

## Capabilities

### New Capabilities

- `docker-image-release`: 定义 Docker 镜像构建、发布、标签、运行时持久化，以及 CPU/NVIDIA CUDA 部署的用户使用说明。

### Modified Capabilities

- 无。

## Impact

- 发布自动化：`.github/workflows/` 新增或扩展 workflow，在 `v*` tag 上构建并发布容器镜像。
- 容器打包：仓库根目录新增 Docker 相关文件，例如 `Dockerfile`、`.dockerignore` 和可选 Compose 示例。
- 运行时配置：启动路径需要支持容器友好的 `config.json`、workspace 数据、模型缓存和 `sharp` CLI 路径，同时不破坏现有脚本安装方式。
- 文档：`README.md`、`README.en.md` 和 release note 需要补充 Docker/GHCR 使用方式、GPU 前置条件和范围边界。
- 依赖与外部系统：发布镜像依赖 Python、ml-sharp、PyTorch CPU/CUDA 构建、GHCR，以及宿主机侧 NVIDIA Container Toolkit。
