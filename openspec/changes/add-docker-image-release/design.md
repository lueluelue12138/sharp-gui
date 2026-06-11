## Context

Sharp GUI 当前通过 GitHub Release 发布源码/前端产物 ZIP，并通过外部网盘链接发布 Windows x64 NVIDIA 完整便携包。运行时本身已经比较接近容器化形态：Flask 在 5050 端口服务 React 构建产物，任务队列通过已安装的 `sharp` CLI 调用推理，`PathContext` 会从配置的 workspace 派生 `inputs/`、`outputs/`、缩略图和本地媒体图库缓存。

真正复杂的部分不是 Web 应用，而是机器学习运行时：PyTorch、CUDA wheel、gsplat 和 Sharp checkpoint 都比较大；Docker 中的 NVIDIA GPU 加速还依赖宿主机驱动和 NVIDIA Container Toolkit。单一通用镜像要么体积过大，要么会误导用户，所以 Docker 支持需要明确的镜像矩阵和清晰的用户说明。

## Goals / Non-Goals

**Goals:**

- 维护者推送 `v*` 发布 tag 时，自动发布 Docker 镜像到 GHCR。
- 首版至少为 Linux amd64 用户提供一个 CPU 镜像和一个 NVIDIA CUDA 镜像。
- 通过文档化的 `/data` volume 持久化用户数据和模型缓存。
- 容器以 React 模式启动 Sharp GUI，监听 5050 端口，不要求用户在容器运行时执行 `install.sh`。
- 文档提供 Docker run 和 Compose 示例，并明确 CUDA 镜像的宿主机 GPU 前置条件。
- 保持现有 ZIP、安装脚本、更新脚本和 Windows 完整便携包流程不变。

**Non-Goals:**

- 首版不提供 macOS/MPS 容器或 Windows 容器。
- 默认镜像不内置 Sharp checkpoint。
- 不承诺无条件 GPU 加速；GPU 加速必须依赖兼容的宿主机 NVIDIA 驱动和 Container Toolkit。
- 首版不引入自托管 GPU CI。
- 不修改上游 `ml-sharp/` 源码。
- 不替换现有 GitHub Release ZIP 或 Windows 完整便携包发布流程。

## Decisions

### Decision: 以 GHCR 作为首选免费镜像仓库

使用 `ghcr.io/lueluelue12138/sharp-gui` 作为官方镜像仓库。

Why:
- GHCR 与现有 GitHub 仓库、release tag 和 `GITHUB_TOKEN` 权限天然集成。
- 大型 ML 镜像不适合通过 GitHub Release asset 或个人网盘链接分发。
- Docker 发布可以与现有 tag 触发发布流程放在同一自动化体系中。

Alternatives considered:
- Docker Hub：用户熟悉，但公开镜像 pull limit 对大型 ML 镜像不够友好。
- GitHub Release asset：适合当前的小型源码 ZIP，不适合镜像 layer 与多标签拉取。
- 外部网盘：已经用于 Windows 完整便携包，但不符合容器原生安装体验。

### Decision: CPU 与 CUDA 镜像分开构建和发布

CPU 与 NVIDIA CUDA 运行时使用不同镜像标签。初始标签应包含不可变版本标签，例如 `v1.2.3-cpu`、`v1.2.3-cuda12.8`，以及移动便利标签，例如 `cpu`、`cuda12.8`。

Why:
- PyTorch CUDA 构建与运行时版本强相关，且体积很大。
- CPU 用户不应该被迫拉取 CUDA runtime layer。
- CUDA 用户需要明确的兼容性信号，而不是含义模糊的 `latest`。

Alternatives considered:
- 单一 all-in-one 镜像：文档更简单，但镜像过大，也仍然不是真正通用。
- 启动时动态安装 torch：可以适配宿主机，但首次启动慢、依赖网络，且可复现性差。
- 只提供 CUDA 镜像：会排除 CPU-only 服务器用户，也无法充分回应 Issue #8。

### Decision: 默认镜像不内置 Sharp checkpoint

默认镜像应把缓存路径设到 `/data/.cache` 下，由 `tools/download_model.py` 或首次推理把 checkpoint 写入 volume。

Why:
- 模型缓存很大，会显著增加镜像体积和 CI 磁盘压力。
- volume 缓存可以让后续运行保持快速，同时避免每次拉镜像都下载巨大模型层。
- 这符合 Docker 习惯：镜像层放应用和运行时，volume 放可变数据。

Alternatives considered:
- 内置 checkpoint 的完整离线镜像：对离线用户方便，但首版体积和发布成本过高。
- 在镜像构建时总是下载模型：首次运行体验更好，但每次构建和拉取都会更重。
- 要求用户手动下载模型到宿主机：镜像更小，但体验差且更容易配置错误。

### Decision: 使用 `/data` 作为容器运行时数据根

容器应以挂载的 `/data` volume 运行。运行时配置应把 `SHARP_CONFIG_FILE`、`workspace_folder`、`TORCH_HOME` 或等价缓存变量，以及 Sharp GUI 用户数据指向 `/data`。

Why:
- 现有路径派生已经支持可配置 workspace。
- 单一 volume 易于文档化，也能覆盖模型输出、上传文件、缩略图、本地媒体图库缓存、配置和模型缓存。
- 避免把容器状态绑定到镜像层或容器用户 home 目录。

Alternatives considered:
- 为配置、输出、缓存拆多个 volume：更显式，但普通用户使用成本更高。
- 继续使用应用目录默认路径：在可写容器中可运行，但更新和重建容器时不安全。
- 直接 bind 仓库内多个目录：接近本地开发方式，但不是好的发布部署形态。

### Decision: 使用 GitHub Actions 构建并推送，首版不做 GPU 运行时自动测试

发布 workflow 应构建前端产物、构建镜像变体、推送到 GHCR，并执行 CPU 级启动/导入冒烟验证。CUDA 镜像可在构建时验证依赖安装，但真实 GPU 执行先作为宿主机相关能力在文档中说明，直到后续有 GPU runner。

Why:
- GitHub-hosted runner 不提供 NVIDIA GPU。
- 构建期检查仍可发现缺文件、入口错误、Python 导入失败和前端构建失败。
- 不让首个有价值的 Docker 发布被新基础设施阻塞。

Alternatives considered:
- 首版就引入自托管 GPU runner：验证更强，但维护成本更高，不是回应 issue 的必要条件。
- 完全不做 CI 验证：实现更快，但发布路径脆弱。
- 只提供本地 Dockerfile：对贡献者有用，但不能满足自动发布诉求。

## Risks / Trade-offs

- [镜像 layer 很大] -> 使用 runtime base image、`.dockerignore`，默认镜像不内置 checkpoint，并在文档说明首次拉取体积预期。
- [CUDA 镜像在部分宿主机不可用] -> 发布带 CUDA 版本的标签，文档说明 NVIDIA Container Toolkit 和驱动要求，同时保留 CPU 镜像。
- [首次推理需要下载大模型] -> 持久化 `/data/.cache`，文档说明首次下载，并保留未来增加 full/offline 镜像的空间。
- [GitHub Actions 磁盘压力] -> build context 排除 `venv/`、`node_modules/`、`inputs/`、`outputs/` 和本地缓存；首版先构建一到两个变体，再扩展矩阵。
- [更新容器后状态丢失] -> 所有文档命令和 Compose 示例都要求挂载 `/data` volume。
- [Docker 部署安全预期不同] -> 保留现有访问控制行为，文档说明 `-p 5050:5050`，不放宽 owner-only 写操作限制。
- [文档与镜像标签漂移] -> workflow 标签矩阵变化时，同步更新 README 和 release note。

## Migration Plan

1. 添加 Docker 构建文件和最小入口脚本，以 React 模式、容器路径启动 `app.py`。
2. 添加由 `v*` tag 和手动 dispatch 触发的 GHCR 发布 workflow。
3. 在中英文 README 中补充 CPU/CUDA 运行命令、Compose 示例、volume 用法和 GPU 前置条件。
4. 本地验证 CPU 镜像；在可用 NVIDIA 宿主机上使用 `docker run --gpus all` 验证 CUDA 镜像。
5. 在下一次 release tag 发布镜像，并用 GHCR 镜像名和支持范围回复 Issue #8。

Rollback:
- 如果镜像发布失败，禁用或回退 Docker workflow。
- 保持现有 Release ZIP 和 Windows 完整便携包发布不受影响。
- 如果发布镜像不可用，删除或隐藏问题 GHCR 标签，再通过 patch release 重新发布修正标签。

Verification points:
- `docker build` 在没有本地 `venv/`、`frontend/node_modules/`、`inputs/`、`outputs/` 的情况下成功。
- 容器启动后可在 `http://127.0.0.1:5050` 访问 React 应用。
- `/data` 可以在容器重建后保留 `config.json`、生成输出、缩略图和模型缓存。
- CPU 镜像可以导入 torch、Flask 和 `sharp`。
- CUDA 镜像可以导入 CUDA-enabled torch；真实 `torch.cuda.is_available()` 在装有 NVIDIA Container Toolkit 的宿主机上手动验证。

## Open Questions

- 首版是否同时提供 `cuda12.6` 和 `cuda12.8`，还是先提供 CPU + `cuda12.8`，根据反馈再补 `cuda12.6`？
- `latest` 应该指向兼容性最好的 CPU 镜像，还是文档中避免使用 `latest`，要求用户显式选择 `cpu` / `cuda12.8`？
- 后续是否需要增加包含 Sharp checkpoint 的 `*-full` 镜像，服务网络条件较差的用户？
