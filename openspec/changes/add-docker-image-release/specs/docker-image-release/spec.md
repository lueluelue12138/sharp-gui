## ADDED Requirements

### Requirement: Docker Release 必须发布 CPU 与 CUDA 镜像变体

Sharp GUI Docker Release MUST 分别提供 CPU 与 NVIDIA CUDA 运行时目标的镜像变体。

#### Scenario: 发布不可变镜像标签

- **WHEN** 维护者发布匹配 `v*` 的版本 tag
- **THEN** 发布自动化 MUST 推送包含版本号和运行时变体的 GHCR 不可变镜像标签
- **AND** 标签集合 MUST 至少包含一个 CPU 变体和一个 NVIDIA CUDA 变体

#### Scenario: 发布便利镜像标签

- **WHEN** 版本化 Docker 发布成功完成
- **THEN** 发布自动化 MUST 为受支持运行时变体推送便利标签
- **AND** 便利标签 MUST 明确运行时目标，例如 `cpu` 或 `cuda12.8`

#### Scenario: CUDA 镜像范围明确

- **WHEN** CUDA 镜像被文档化或发布
- **THEN** 运行时目标 MUST 标明 CUDA runtime 系列
- **AND** 文档 MUST 说明 GPU 加速还需要兼容的宿主机 NVIDIA 驱动和 NVIDIA Container Toolkit

### Requirement: Docker 运行时必须通过挂载数据卷持久化应用状态

Sharp GUI Docker 容器 MUST 将可变运行状态保存在镜像层之外，并写入文档化的数据卷。

#### Scenario: 用户使用数据卷运行容器

- **WHEN** 用户按文档挂载 `/data` volume 启动 Docker 镜像
- **THEN** Sharp GUI MUST 使用该 volume 保存运行时配置、上传输入、生成输出、缩略图、本地媒体图库缓存和模型缓存
- **AND** 使用同一 volume 重建容器 MUST 保留这些文件

#### Scenario: 容器无需安装脚本即可启动

- **WHEN** 用户启动已发布的 Docker 镜像
- **THEN** Sharp GUI MUST 在不要求用户运行 `install.sh`、`install.bat`、`build.sh` 或 `npm install` 的情况下启动
- **AND** 容器 MUST 在 `5050` 端口服务 React 前端

#### Scenario: 默认镜像不要求内置模型缓存

- **WHEN** 默认 Docker 镜像被构建或发布
- **THEN** 镜像层 MUST NOT 要求内置 Sharp checkpoint
- **AND** 镜像 MUST 支持从挂载数据卷缓存下载或复用 checkpoint

### Requirement: Docker 发布自动化必须通过 GitHub Actions 构建并推送镜像

Sharp GUI Docker 镜像 MUST 由仓库自动化构建和发布，而不是依赖本地手动上传。

#### Scenario: 版本 tag 触发镜像发布

- **WHEN** 匹配 `v*` 的版本 tag 被推送
- **THEN** GitHub Actions MUST 构建配置的 Docker 镜像变体
- **AND** GitHub Actions MUST 将成功构建的镜像推送到仓库命名空间下的 GHCR

#### Scenario: Docker build context 排除本地运行产物

- **WHEN** GitHub Actions 构建 Docker 镜像
- **THEN** build context MUST 排除本地虚拟环境、前端 `node_modules`、生成输入、生成输出、本地缓存和其他非发布产物
- **AND** 构建 MUST 使用仓库源码和 lockfile，而不是开发机运行目录

#### Scenario: 自动化执行冒烟验证

- **WHEN** Docker 镜像变体在 CI 中构建
- **THEN** workflow MUST 执行与当前 runner 能力匹配的冒烟验证
- **AND** CPU 级验证 MUST 确认核心运行时导入和容器启动路径可用
- **AND** CUDA GPU 执行 MAY 在具备 GPU runner 前作为手动验证项写入文档

### Requirement: Docker 使用文档必须双语且可操作

Sharp GUI MUST 在中文和英文用户文档中说明 Docker 使用方式。

#### Scenario: 用户阅读 Docker 快速开始

- **WHEN** 用户阅读 `README.md` 或 `README.en.md` 中的 Docker 章节
- **THEN** 文档 MUST 提供 CPU 与 NVIDIA CUDA 用法的可复制命令
- **AND** 命令 MUST 包含端口映射和持久化 volume 挂载

#### Scenario: 用户阅读 GPU 前置条件

- **WHEN** 用户阅读 Docker GPU 说明
- **THEN** 文档 MUST 说明 CUDA 镜像需要宿主机侧 NVIDIA 驱动和 NVIDIA Container Toolkit
- **AND** 文档 MUST 展示启用 GPU 访问的容器运行方式

#### Scenario: 用户阅读包含 Docker 支持的 Release Note

- **WHEN** 某个 release 包含 Docker 镜像支持
- **THEN** release note MUST 提到 GHCR 镜像可用性、CPU/CUDA 变体选择和持久化数据卷
- **AND** 中文与英文 release 文案 MUST 保持同步
