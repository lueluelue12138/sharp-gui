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
- Docker bridge 网络下，宿主机浏览器必须能通过正式的 owner 引导流程完成门禁、设置、重启、本地相册目录等 owner-only 配置。
- 前端需要以现有 Apple 玻璃态设计语言展示 Docker 管理员验证和容器路径提示，不使用浏览器原生弹窗或临时样式块。
- 保持现有 ZIP、安装脚本、更新脚本和 Windows 完整便携包流程不变。

**Non-Goals:**

- 首版不提供 macOS/MPS 容器或 Windows 容器。
- 默认镜像不内置 Sharp checkpoint。
- 不承诺无条件 GPU 加速；GPU 加速必须依赖兼容的宿主机 NVIDIA 驱动和 Container Toolkit。
- 首版不引入自托管 GPU CI。
- 不修改上游 `ml-sharp/` 源码。
- 不替换现有 GitHub Release ZIP 或 Windows 完整便携包发布流程。
- 不通过信任 `X-Forwarded-For`、`Forwarded`、`X-Real-IP` 等转发头授予 owner 权限。
- 不把 Docker 网桥网段、私有网段或 reverse proxy 来源 IP 默认视为 owner。
- 不要求用户依赖 `--network host` 才能完成 Docker 管理配置。

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

### Decision: 为 Docker 增加 owner bootstrap 会话，而不是放宽本机 IP 判断

Docker 镜像应提供一个显式的管理员引导 token。容器启动时可以从环境变量读取 token，也可以在 `/data` 下生成持久 token 文件并把取用方式打印到日志。浏览器通过新的 owner bootstrap API 验证 token 后，后端发放独立的 HttpOnly owner session cookie；后续 owner-only API 同时接受真实 localhost owner 和有效 owner session。

```text
Docker bridge 默认路径

宿主机浏览器
  http://127.0.0.1:5050
        │
        │ 端口映射/NAT
        ▼
Flask in container
  remote_addr = 172.17.0.1  ≠ 127.0.0.1
        │
        ├─ 普通 localhost 判断失败
        ▼
Docker owner bootstrap
  输入/提交 token -> owner HttpOnly cookie -> owner-only API 可用
```

Why:
- 默认 Docker bridge 下，宿主机浏览器访问 `127.0.0.1:5050` 时，容器内 Flask 看到的来源通常是 Docker 网桥地址，而不是 loopback。
- owner-only 能力覆盖访问码设置、门禁配置、workspace 修改、重启、本地相册目录管理、删除和批量转换，不能让 Docker 用户只能手改配置文件。
- token 引导是显式授权，不依赖网络拓扑猜测；它能在 Linux、Docker Desktop、NAS、Compose 和反代场景保持一致。
- 使用 HttpOnly cookie 可以延续现有会话模型，前端不需要长期保存管理员 secret。

Token and session rules:
- 环境变量建议使用 `SHARP_OWNER_TOKEN`，适合 Compose、NAS 面板和自动部署场景；为空时容器入口应生成高强度随机 token，并保存到 `/data/owner-token.txt` 或等价路径。
- token 文件必须位于 `/data`，随 volume 持久化；重建容器不应无故更换 token，除非用户删除或显式轮换。
- 后端不得在 API 响应中泄露完整 token；状态接口只暴露 `docker_mode`、`owner_bootstrap_available`、`owner_authenticated` 等摘要。
- owner session 应与普通访问码 session 分离，避免普通局域网访问码登录被提升为 owner。可选实现是新增 `sharp_gui_owner` cookie，payload 中包含 `scope: "owner"`、`session_version`、过期时间和 nonce，并使用现有 `session_secret` 签名。
- 撤销远程会话或修改访问控制配置时，应能让 owner session 随 `session_version` 失效；后续可增加单独的 owner session 轮换入口。
- owner bootstrap API 必须走同源请求校验、失败限速和固定时间比较，不能接受 query string token，避免日志、Referer 或浏览器历史泄露。

Alternatives considered:
- Linux `--network host`：可以让后端看到 loopback，但不适用于 Docker Desktop/NAS，且削弱隔离，不应作为正式方案。
- 信任 `172.17.0.1` 或私有网段：在端口映射、NAS、反代或多层网络中可能把真实局域网用户误判为 owner，安全边界不清晰。
- 手工编辑 `/data/config.json`：可作为故障恢复说明，但不是可接受的产品体验。
- 启动参数直接关闭 owner-only 限制：会把删除、重启、路径配置暴露给局域网，不符合现有安全模型。

### Decision: Docker 路径配置使用容器内路径，并在界面中明确提示挂载关系

Docker 部署下，Sharp GUI 设置页中的 workspace 和本地相册路径应解释为容器内路径。用户要访问宿主机/NAS 上的目录，必须先通过 `-v /host/path:/container/path` 或 Compose volumes 挂载，然后在 UI 中填写 `/container/path`。

```text
宿主机/NAS 路径                 Docker volume                 Sharp GUI 设置
/mnt/photos ───────────────▶ /media/photos ───────────────▶ /media/photos
/srv/sharp-workspace ──────▶ /data/workspace ─────────────▶ /data/workspace
```

Why:
- 浏览器运行在宿主机，后端运行在容器，原生文件夹选择器没有可靠方式替容器选择宿主机路径。
- 让 UI 显示容器路径语义，比伪装成本机路径更准确，也能减少 NAS/Compose 用户配置混乱。
- 这不改变现有本机安装体验；只有检测到 Docker 运行时才展示 Docker 路径提示和禁用不适用的本机文件夹浏览能力。

UI requirements:
- 门禁页在 `setup_required` 且检测到 Docker owner bootstrap 可用时，应展示“Docker 管理员验证”入口：一个 token 密码输入框、清晰的短说明、主要按钮和错误反馈。
- 设计必须延续 `AccessGate` 和 `Settings` 现有 Apple 玻璃态：半透明 panel、8px 左右圆角、柔和边框、系统字体、lucide 图标、明确 hover/focus-visible 状态。
- 设置页 Docker 提示应使用轻量玻璃态提示区域或现有通用组件，不使用 `alert()`、`prompt()`、浏览器原生 `confirm()` 或视觉突兀的大色块。
- 新增用户可见文案必须同步维护 `frontend/src/i18n/en.json` 和 `frontend/src/i18n/zh.json`，新 key 使用 `access*`、`auth*` 或 `docker*` camelCase 前缀。
- 需要支持 375 / 768 / 1024 / 1440 宽度，无按钮文字溢出、提示遮挡或移动端不可达控件。

## Risks / Trade-offs

- [镜像 layer 很大] -> 使用 runtime base image、`.dockerignore`，默认镜像不内置 checkpoint，并在文档说明首次拉取体积预期。
- [CUDA 镜像在部分宿主机不可用] -> 发布带 CUDA 版本的标签，文档说明 NVIDIA Container Toolkit 和驱动要求，同时保留 CPU 镜像。
- [首次推理需要下载大模型] -> 持久化 `/data/.cache`，文档说明首次下载，并保留未来增加 full/offline 镜像的空间。
- [GitHub Actions 磁盘压力] -> build context 排除 `venv/`、`node_modules/`、`inputs/`、`outputs/` 和本地缓存；首版先构建一到两个变体，再扩展矩阵。
- [更新容器后状态丢失] -> 所有文档命令和 Compose 示例都要求挂载 `/data` volume。
- [Docker 部署安全预期不同] -> 保留现有访问控制边界，增加显式 owner bootstrap 会话，不放宽 owner-only 写操作限制。
- [owner token 泄露] -> 默认生成高强度 token、只保存到 `/data`、不经 API 回显完整值、提交时使用 JSON body、失败限速，并建议用户把服务暴露到公网前设置反代 HTTPS 和强访问码。
- [路径配置混淆] -> Docker UI 和文档统一强调“先挂载宿主机目录，再填写容器内路径”，并把原生文件夹选择能力限制在本机安装可用场景。
- [文档与镜像标签漂移] -> workflow 标签矩阵变化时，同步更新 README 和 release note。

## Migration Plan

1. 添加 Docker 构建文件和最小入口脚本，以 React 模式、容器路径启动 `app.py`。
2. 添加由 `v*` tag 和手动 dispatch 触发的 GHCR 发布 workflow。
3. 增加 Docker owner bootstrap token 生成、验证 API、owner session 和权限矩阵测试。
4. 更新门禁页和设置页，在 Docker 模式下提供管理员验证和容器路径提示，保持现有 Apple 玻璃态风格与双语 i18n。
5. 在中英文 README 中补充 CPU/CUDA 运行命令、Compose 示例、volume 用法、GPU 前置条件、owner token 使用方式和宿主机目录挂载说明。
6. 本地验证 CPU 镜像；在可用 NVIDIA 宿主机上使用 `docker run --gpus all` 验证 CUDA 镜像。
7. 在下一次 release tag 发布镜像，并用 GHCR 镜像名和支持范围回复 Issue #8。

Rollback:
- 如果镜像发布失败，禁用或回退 Docker workflow。
- 保持现有 Release ZIP 和 Windows 完整便携包发布不受影响。
- 如果发布镜像不可用，删除或隐藏问题 GHCR 标签，再通过 patch release 重新发布修正标签。

Verification points:
- `docker build` 在没有本地 `venv/`、`frontend/node_modules/`、`inputs/`、`outputs/` 的情况下成功。
- 容器启动后可在 `http://127.0.0.1:5050` 访问 React 应用。
- `/data` 可以在容器重建后保留 `config.json`、生成输出、缩略图和模型缓存。
- Docker bridge 模式下，不使用 `--network host` 时，宿主机浏览器可以通过 owner token 获取 owner 权限并完成首次访问码设置。
- 未提供或提供错误 owner token 时，owner-only API 仍返回 `OWNER_REQUIRED`，普通访问码会话不能执行 owner-only API。
- Docker 模式下，设置页能清楚提示容器内路径与 volume 挂载关系；前端在桌面和移动宽度下无布局溢出。
- CPU 镜像可以导入 torch、Flask 和 `sharp`。
- CUDA 镜像可以导入 CUDA-enabled torch；真实 `torch.cuda.is_available()` 在装有 NVIDIA Container Toolkit 的宿主机上手动验证。

## Open Questions

- 首版是否同时提供 `cuda12.6` 和 `cuda12.8`，还是先提供 CPU + `cuda12.8`，根据反馈再补 `cuda12.6`？
- `latest` 应该指向兼容性最好的 CPU 镜像，还是文档中避免使用 `latest`，要求用户显式选择 `cpu` / `cuda12.8`？
- 后续是否需要增加包含 Sharp checkpoint 的 `*-full` 镜像，服务网络条件较差的用户？
- owner token 文件是否固定为 `/data/owner-token.txt`，还是允许通过 `SHARP_OWNER_TOKEN_FILE` 覆盖？
- owner session 默认有效期是否沿用 `session_days`，还是使用较短的独立默认值，例如 7 天？
