## 1. 容器运行时文件

- [x] 1.1 新增根目录 `.dockerignore`，排除本地虚拟环境、`node_modules`、生成输入/输出、本地缓存、发布产物和其他不应进入镜像 build context 的内容。
- [x] 1.2 新增 CPU 与 CUDA 变体所需的 Docker 构建文件，使用合适的 runtime base，并基于仓库源码构建，不依赖开发机运行目录。
- [x] 1.3 新增容器入口或启动路径，设置 React 模式、`5050` 端口、`/data` workspace/config/cache 路径、Python 编码变量和 `sharp` CLI 路径。
- [x] 1.4 确保容器镜像运行时无需执行 `install.sh`、`install.bat`、`build.sh` 或 `npm install` 即可启动 Sharp GUI。

## 2. 运行时持久化与模型缓存

- [x] 2.1 将容器内 `config.json`、workspace 数据、inputs、outputs、缩略图、本地媒体图库缓存和模型缓存路由到文档化的 `/data` volume。
- [x] 2.2 确保默认镜像不把 Sharp checkpoint 写入镜像层，并可通过 `/data` 缓存复用或下载 checkpoint。
- [x] 2.3 验证使用同一 `/data` volume 重建容器后，配置、生成输出和模型缓存文件仍然保留。

## 3. GHCR 发布自动化

- [x] 3.1 新增 GitHub Actions workflow 或扩展现有 release workflow，在 `v*` tag 和手动 dispatch 时构建 Docker 镜像。
- [x] 3.2 为每个镜像变体发布不可变 GHCR 标签，例如 `vX.Y.Z-cpu` 和 `vX.Y.Z-cuda12.8`。
- [x] 3.3 为受支持变体发布明确的便利标签，例如 `cpu` 和 `cuda12.8`，避免依赖含义模糊的 GPU `latest`。
- [x] 3.4 配置 workflow 权限和镜像 metadata label，使 GHCR package 正确关联到当前仓库。
- [x] 3.5 保持现有 GitHub Release ZIP 与 Windows 完整便携包发布流程不变。

## 4. 验证

- [x] 4.1 本地或 CI 构建 CPU 镜像，并验证 Flask、torch 和 `sharp` 的 Python 导入可用。
- [x] 4.2 运行 CPU 镜像，验证 React 应用可通过 `http://127.0.0.1:5050` 访问。
- [x] 4.3 构建 CUDA 镜像，并验证容器内 CUDA-enabled torch 可成功导入。
- [ ] 4.4 在可用的 NVIDIA Docker 宿主机上使用 GPU 权限运行 CUDA 镜像，验证 `torch.cuda.is_available()` 和 Sharp GUI 基础启动路径。
- [x] 4.5 运行与打包相关的现有项目检查；条件允许时执行前端构建和后端测试。

## 5. 文档与发布说明

- [x] 5.1 更新 `README.md`，加入中文 Docker 快速开始命令，覆盖 CPU 与 NVIDIA CUDA 变体，并包含 `-p 5050:5050` 与 `/data` volume 挂载。
- [x] 5.2 更新 `README.en.md`，加入匹配的英文 Docker 快速开始命令和同样的范围边界。
- [x] 5.3 文档说明 CUDA 镜像所需的 NVIDIA 驱动和 NVIDIA Container Toolkit 前置条件，并给出启用 GPU 访问的运行命令。
- [x] 5.4 文档说明默认镜像不内置 Sharp checkpoint，首次使用可能会写入 `/data` 模型缓存。
- [x] 5.5 更新 release note 规范或 release workflow 正文，使包含 Docker 支持的 release 提到 GHCR 镜像、变体选择和持久化数据卷。
- [x] 5.6 准备一段简洁的 GitHub Issue #8 回复，引导用户使用已发布的 GHCR 镜像，并说明 CPU/CUDA 支持范围。
