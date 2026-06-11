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

### Requirement: Docker 部署必须支持正式的 owner 引导权限

Sharp GUI Docker 部署 MUST 提供不依赖 host network、不依赖 Docker 网桥 IP 信任的 owner 引导流程。

#### Scenario: Docker bridge 下完成首次 owner 配置

- **WHEN** 用户以默认 Docker bridge 端口映射启动容器
- **AND** 宿主机浏览器访问 `http://127.0.0.1:5050`
- **THEN** 用户 MUST 能通过 Docker owner bootstrap token 获取 owner 权限
- **AND** 用户 MUST 能完成首次访问码设置和门禁配置
- **AND** 用户 MUST NOT 被要求改用 `--network host` 或手工编辑 `config.json`

#### Scenario: 容器生成或接收 owner bootstrap token

- **WHEN** 容器启动时提供 `SHARP_OWNER_TOKEN`
- **THEN** 后端 MUST 使用该 token 作为 Docker owner bootstrap secret
- **WHEN** 容器启动时未提供 `SHARP_OWNER_TOKEN`
- **THEN** 容器 MUST 生成高强度随机 token
- **AND** token MUST 保存到挂载的 `/data` volume 中，便于容器重建后继续使用
- **AND** 启动日志 MAY 提示 token 文件路径，但 API 响应 MUST NOT 回显完整 token

#### Scenario: owner bootstrap 授予独立 owner session

- **WHEN** 用户提交正确的 Docker owner bootstrap token
- **THEN** 后端 MUST 返回成功认证状态
- **AND** 后端 MUST 设置 HttpOnly owner session cookie
- **AND** 后续同源请求 MUST 能使用该 owner session 访问 owner-only API
- **AND** 普通访问码 session MUST NOT 被提升为 owner session

#### Scenario: 错误 owner bootstrap 不放宽权限

- **WHEN** 用户未提供 token 或提交错误 token
- **THEN** 后端 MUST 拒绝 owner bootstrap 请求
- **AND** 后端 MUST NOT 设置 owner session cookie
- **AND** owner-only API MUST 继续返回 owner 权限错误
- **AND** 失败验证 SHOULD 受到与登录类似的延迟或限速保护

#### Scenario: owner 权限不得来自不可信网络头或网段

- **WHEN** 请求带有 `X-Forwarded-For`、`Forwarded`、`X-Real-IP` 或其他客户端可控转发头
- **THEN** 后端 MUST NOT 仅凭这些头授予 owner 权限
- **WHEN** 请求来源是 Docker bridge、私有网段、反向代理或 NAS 网关地址
- **THEN** 后端 MUST NOT 默认将该来源视为 owner
- **AND** owner 权限 MUST 来自真实 loopback 判断或有效 owner session

### Requirement: Docker 模式必须清楚呈现管理员验证与路径配置体验

Sharp GUI 前端 MUST 在 Docker 模式下提供可用、清晰且符合现有 Apple 玻璃态风格的管理员验证与路径配置提示。

#### Scenario: 门禁页显示 Docker 管理员验证入口

- **WHEN** 访问码尚未配置
- **AND** 后端状态显示 Docker owner bootstrap 可用
- **THEN** 门禁页 MUST 显示 Docker 管理员验证入口
- **AND** 入口 MUST 包含 token 密码输入、提交按钮、简短说明和错误反馈
- **AND** 验证成功后 MUST 刷新认证状态并允许 owner 执行首次设置

#### Scenario: Docker UI 遵循现有视觉规范

- **WHEN** 前端新增 Docker 管理员验证或路径提示 UI
- **THEN** UI MUST 使用现有 CSS Modules、CSS Variables、lucide 图标和 Apple 玻璃态层级
- **AND** UI MUST NOT 使用浏览器原生 `alert()`、`prompt()`、`confirm()` 作为主要交互
- **AND** 新增用户可见文案 MUST 同步维护 `frontend/src/i18n/en.json` 与 `frontend/src/i18n/zh.json`
- **AND** 新增 i18n key MUST 使用 camelCase

#### Scenario: 设置页解释容器内路径

- **WHEN** 应用运行在 Docker 模式
- **AND** 用户查看 workspace 或本地媒体相册目录设置
- **THEN** 前端 MUST 说明这些路径是容器内路径
- **AND** 前端 MUST 提示用户先通过 Docker volume 或 Compose volumes 挂载宿主机/NAS 目录
- **AND** 文档 MUST 给出宿主机路径到容器路径的示例映射

#### Scenario: Docker 路径配置不依赖不适用的宿主机文件选择器

- **WHEN** 应用运行在 Docker 模式
- **THEN** 前端 SHOULD 避免把原生文件夹选择器呈现为主要路径配置方式
- **AND** 用户 MUST 能手动输入容器内路径
- **AND** 后端 MUST 仍按 owner 权限保护路径写入和本地相册目录管理

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
- **AND** 文档 MUST 说明 owner bootstrap token 的获取和使用方式

#### Scenario: 用户阅读 GPU 前置条件

- **WHEN** 用户阅读 Docker GPU 说明
- **THEN** 文档 MUST 说明 CUDA 镜像需要宿主机侧 NVIDIA 驱动和 NVIDIA Container Toolkit
- **AND** 文档 MUST 展示启用 GPU 访问的容器运行方式

#### Scenario: 用户阅读包含 Docker 支持的 Release Note

- **WHEN** 某个 release 包含 Docker 镜像支持
- **THEN** release note MUST 提到 GHCR 镜像可用性、CPU/CUDA 变体选择和持久化数据卷
- **AND** 中文与英文 release 文案 MUST 保持同步

#### Scenario: 用户配置宿主机或 NAS 目录

- **WHEN** 用户阅读 Docker 路径配置说明
- **THEN** 文档 MUST 说明 Sharp GUI 中填写的是容器内路径
- **AND** 文档 MUST 展示至少一个 bind mount 示例，例如 `/host/photos:/media/photos`
- **AND** 文档 MUST 说明不应期望容器直接浏览未挂载的宿主机文件系统
