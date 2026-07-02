# 项目架构总览

## 架构模式

Sharp GUI 采用 **前后端分离 + 双前端模式** 架构：

```
┌─────────────────────────────────────────────────┐
│  浏览器（桌面 / 移动端 / VR）                      │
│  ┌───────────────────┬────────────────────────┐  │
│  │  React 19 前端     │  Three.js + Spark 渲染  │  │
│  │  (Zustand + i18n) │  (WebGL / WebXR)       │  │
│  └────────┬──────────┴─────────┬──────────────┘  │
│           │ fetch              │ .ply/.splat      │
└───────────┼────────────────────┼──────────────────┘
            │ /api/*             │ /files/*
┌───────────┼────────────────────┼──────────────────┐
│  Flask 后端 (app.py 兼容入口 + backend/ 包)        │
│  ┌────────┴───────┐  ┌────────┴──────────────┐   │
│  │  routes/API     │  │  static files service │   │
│  │  + security     │  │  (白名单服务根)        │   │
│  └────────┬───────┘  └───────────────────────┘   │
│           │ services / PathContext / TaskManager  │
│  ┌────────┴───────────────────────────────────┐  │
│  │  TaskManager (queue.Queue + threading.Lock) │  │
│  │  → image_sharp: sharp predict               │  │
│  │  → video_3dgs: Nerfstudio/Splatfacto pipeline│  │
│  └────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
            │ subprocess
┌───────────┴───────────────────────────────────────┐
│  AI / reconstruction engines                       │
│  Apple ml-sharp；Nerfstudio/Splatfacto + COLMAP    │
└───────────────────────────────────────────────────┘
```

## 双前端模式

通过环境变量 `SHARP_FRONTEND_MODE` 切换：

| 模式 | 值 | 说明 |
|------|----|------|
| **React**（默认） | `react` | 现代 SPA，构建产物在 `frontend/dist/` |
| **Legacy** | `legacy` | 单文件版，`templates/index.html`（约 4,555 行） |

启动脚本 `run.sh` 通过 `--legacy` 参数切换。

## 目录结构

```
sharp-gui/
├── app.py                    # Flask 兼容入口：暴露 app，python app.py 时启动服务
├── backend/                  # 模块化后端包
│   ├── app_factory.py        #   create_app()：创建 Flask app、注册 hooks/routes、挂载 TaskManager
│   ├── server.py             #   run_server()、监听地址、HTTPS、重启支持
│   ├── runtime.py            #   环境变量、BASE_DIR、verbose 日志、Sharp 命令/设备解析
│   ├── config.py             #   config.json 读写与 access_control normalize
│   ├── paths.py              #   PathContext：workspace/inputs/outputs/cache 派生
│   ├── security/             #   LAN 门禁、权限矩阵、request hooks
│   ├── services/             #   模型资产/本地媒体图库、视频重建、任务队列、导出、静态文件、文件夹选择
│   └── routes/               #   auth/gallery/model_assets/photo_gallery/video_reconstruction/tasks/settings/files/export/frontend
├── config.json               # 运行时配置（workspace_folder, photo_gallery_roots_by_workspace, access_control）
├── install.sh / install.bat  # 一键安装脚本（Python/Git/CUDA/依赖/模型/证书）
├── run.sh / run.bat          # 启动脚本（支持 --legacy）
├── build.sh / build.bat      # 前端构建脚本
├── release.sh / release.bat  # 发布打包脚本
├── update.sh / update.bat    # 自动更新脚本
│
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── api/              #   API 层（client.ts + 功能模块，含 modelAssets.ts/photoGallery.ts）
│   │   ├── components/       #   组件（auth/common/gallery/modelAssets/photoGallery/layout/viewer）
│   │   │   ├── common/       #     通用 UI：Button, Icons, ImageViewer, Loading, Modal, ConfirmDialog, SelectMenu, TextInputDialog
│   │   │   ├── auth/         #     局域网门禁：AccessGate, AccessSetupPrompt
│   │   │   ├── gallery/      #     模型图库：GalleryItem, GalleryList
│   │   │   ├── modelAssets/  #     模型资产库：LibraryView, Grid, Toolbar, DetailsPanel
│   │   │   ├── photoGallery/ #     本地媒体图库：PhotoAlbumList, PhotoGalleryView, PhotoMasonryGrid, PhotoToolbar
│   │   │   ├── layout/       #     布局：Sidebar, ControlsBar, Help, Settings, TaskQueue
│   │   │   └── viewer/       #     查看器：ViewerCanvas, QuickControls, ViewerRevealEffectsRail, GyroIndicator, VirtualJoystick, SpeedTooltip
│   │   ├── constants/        #   Spark / LoD / XR 相关常量
│   │   ├── hooks/            #   自定义 Hooks（useViewer, useXR, useKeyboard, useGyroscope, useJoystick, useGalleryVirtualizer 等）
│   │   ├── i18n/             #   国际化（index.ts + en.json + zh.json）
│   │   ├── store/            #   Zustand 状态管理（useAppStore.ts）
│   │   ├── styles/           #   全局样式（variables.css, animations.css, global.css）
│   │   ├── types/            #   TypeScript 类型定义
│   │   └── utils/            #   工具函数（camera.ts, format.ts, gallery.ts, modelAssets.ts, viewerRevealEffects.ts）
│   ├── vite.config.ts        #   Vite 配置（代理、分包、HTTPS）
│   ├── tsconfig.json         #   TypeScript 配置（strict mode）
│   └── eslint.config.js      #   ESLint flat config
│
├── templates/                # Legacy 单文件前端
│   ├── index.html            #   完整 Legacy SPA（约 4,555 行）
│   └── share_template.html   #   Spark 2.0 独立分享页模板（约 1,333 行）
│
├── static/lib/               # 预打包的 Three.js + GaussianSplats3D（Legacy 版本使用，不可修改）
├── tools/                    # 工具脚本
│   ├── detect_cuda.py        #   CUDA 版本检测
│   ├── download_model.py     #   模型下载（多源 + SHA256 校验）
│   ├── generate_cert.py      #   SSL 证书生成
│   ├── install_torch.py      #   CUDA/CPU PyTorch 安装选择
│   └── update.py             #   自动更新逻辑
│
├── ml-sharp/                 # Apple ML-Sharp 引擎（⚠️ 不可修改）
├── inputs/                   # 用户上传的图片
├── outputs/                  # 生成的 3D 模型（.ply + 自动转换 .spz）
├── model-assets/             # 导入模型与模型资产封面缓存（位于 workspace_folder）
├── .model-asset-library/     # 模型资产索引与用户编辑信息（位于 workspace_folder）
├── .video-reconstruction/    # 视频重建上传缓存、jobs 与中间文件（位于 workspace_folder）
├── .photo-gallery-cache/     # 本地媒体图库 catalog、每相册索引、照片缩略图、视频 poster 与临时 ZIP（位于 workspace_folder）
├── openspec/                 # OpenSpec 变更与能力规格
└── docs/                     # GitHub Pages 产品介绍页
```

## 关键依赖版本

### 前端 (package.json)

| 依赖 | 版本 | 说明 |
|------|------|------|
| react / react-dom | ^19.2.0 | UI 框架 |
| zustand | ^5.0.10 | 状态管理 |
| three | ^0.180.0 | 3D 渲染引擎 |
| @mkkellogg/gaussian-splats-3d | - | 已移除，替换为 Spark |
| @sparkjsdev/spark | ^2.0.0 | WASM 加速高斯溅射渲染器（稳定版） |
| i18next | ^25.8.0 | 国际化核心 |
| react-i18next | ^16.5.3 | React 绑定 |
| typescript | ~5.9.3 | 类型系统 |
| vite | ^7.2.4 | 构建工具 |
| eslint | ^9.39.1 | 代码检查 |

### 后端

| 依赖 | 说明 |
|------|------|
| Python 3.10~3.13 | 运行环境 |
| Flask | Web 框架 |
| Pillow (PIL) | 图片处理 / 缩略图 |
| numpy | PLY 数据处理 |
| plyfile | PLY 文件解析 |
| ml-sharp (sharp CLI) | AI 推理引擎 |
| ffmpeg / ffprobe | 视频重建抽帧、元数据、poster 和源视频缩略图 |
| Nerfstudio / Splatfacto / gsplat | 视频 3DGS 稳定重建路线 |
| COLMAP | Nerfstudio 视频数据处理中的位姿/稀疏几何估计 |
| pytest | 后端开发/重构验证（仅开发依赖，见 `requirements-dev.txt`） |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SHARP_FRONTEND_MODE` | `react` | 前端模式：`react` 或 `legacy` |
| `SHARP_DEBUG` | 关闭 | 设为 `1` 开启 Flask 调试器 + 源码热重载（向客户端返回堆栈、暴露交互式调试器、改 `.py` 自动重启）。有安全风险，仅本机排障使用 |
| `SHARP_VERBOSE` | 关闭 | 设为 `1` 开启详细诊断日志文件，`run.sh --verbose` / `run.bat --verbose` 会设置 |
| `SHARP_LOG_LEVEL` | `INFO`（verbose 时 `DEBUG`） | 应用日志级别 |
| `SHARP_HTTP_LOGS` | 关闭 | 设为 `1` 时输出 Werkzeug HTTP 请求日志；默认关闭以避免缩略图/轮询请求刷屏 |
| `SHARP_LOG_FILE` | `sharp-gui-verbose.log` | 详细诊断日志输出路径 |
| `SHARP_BIND_HOST` | 跟随门禁设置 | 覆盖监听地址；不设时由 `lan_bind_enabled` 决定（开 `0.0.0.0` / 关 `127.0.0.1`） |
| `SHARP_LAN_IP` | 自动检测 | 局域网访问 IP |
| `SHARP_DEVICE` | 自动选择 | 推理设备：`cpu` / `cuda` / `mps` |
| `PYTHONHTTPSVERIFY` | `0`（安装时） | 绕过 SSL 验证（企业/学校网络） |

> `SHARP_DEBUG` 同时控制调试器、堆栈泄露与源码热重载（三者都需要 reloader 关闭才能让 `/api/restart` 正确重新绑定监听地址，详见 backend-guide）。默认全部关闭；`SHARP_DEBUG=1` 时全部开启，仅本机排障使用。

## 端口与协议

- 默认端口：**5050**
- HTTPS：自动检测项目根目录下 `cert.pem` / `key.pem`
- 开发代理：Vite dev server 将 `/api` 和 `/files` 代理到 `localhost:5050`
- 监听地址由 `access_control.lan_bind_enabled` 决定：`true` → `0.0.0.0`（局域网可达），`false` → `127.0.0.1`（仅本机）；`SHARP_BIND_HOST` 可覆盖。
- 可选局域网门禁由 `access_control.enabled` 控制。HTTPS 负责传输加密，访问码负责浏览资格；owner-only 写操作仍只接受 localhost。
- `/files/*` 静态服务仅限白名单根（`outputs/`、历史缩略图、`model-assets/imports/` 与 `model-assets/thumbnails/`），敏感文件（`config.json`、`.model-asset-library/index.json`、证书私钥、`app.py`）一律拒绝，且不随门禁开关放宽。

## 3D 渲染引擎迁移说明

项目 3D 渲染层已从 `@mkkellogg/gaussian-splats-3d`（已停止维护）迁移至 `@sparkjsdev/spark` 2.0 稳定版：

- **React 前端**（`frontend/`）：使用 Spark（SplatMesh + SparkRenderer + LoD + RAD 可选流式加载），支持 PLY / SPLAT / SPZ / RAD
- **Legacy 前端**（`templates/index.html` + `static/lib/`）：仍使用预打包的 GaussianSplats3D，不修改
- **导出分享**（`share_template.html`）：已迁移到 Spark 2.0，后端将 Three.js / OrbitControls / Spark 作为 data URL 嵌入独立 HTML

## 模型与本地媒体图库

- 后端推理仍生成 `.ply` 原始模型。
- 生成完成后自动转换 `.spz` 紧凑模型；用户设置可在 PLY / SPZ 之间选择默认查看和下载格式。
- 模型资产库通过 `/api/model-assets` 统一展示生成模型与导入的 PLY/SPZ/SPLAT/RAD；旧 `/api/gallery` 仍作为兼容模型列表保留，不应继续承载导入、详情面板、筛选排序等新主路径。
- 模型资产导入文件写入 `{workspace}/model-assets/imports/`，模型封面写入 `{workspace}/model-assets/thumbnails/`，索引和用户编辑信息写入 `{workspace}/.model-asset-library/index.json`；这些路径必须由 `PathContext` 派生，不得在前端或路由层拼接绝对路径。
- 模型资产库主区域使用游标式滚动增量加载，不显示分页器或每页数量选择；网格密度只影响展示列数，筛选、排序或密度变化只重置游标并请求下一批，不触发全目录重扫。
- 模型资产打开、下载和近期模型展示应通过 `resolveModelAssetSource` 或等价逻辑遵守 `model_format` 默认格式偏好，并在首选格式缺失时回退到资产可用文件。
- 模型资产详情可从 PLY/SPLAT 解析部分点数或属性；SPZ/RAD 的包围盒、坐标系、LoD、chunk 等高级信息只有 sidecar 或源格式明确提供时才展示，不能为了填空伪造“计算结果”。
- 近期模型侧栏是资产库的辅助入口：可独立滚动增量查询，同时保持“近期模型/查看全部”和底部“储存占用”区域固定；按钮样式复用现有 hover/focus 图标按钮，不做共享胶囊背景。
- 视频重建生成的模型也写入 `outputs/`，并额外写入同名 `.meta.json` 记录来源视频、模式、质量、引擎和受控源视频引用；前端不得看到绝对磁盘路径。
- 视频生成模型应复用现有模型图库：缩略图优先使用源视频封面帧；hover 操作中可提供原视频预览入口；删除拖入视频生成的模型时可清理受控上传缓存，但不得删除本地相册原视频。
- 视频 3DGS 重建稳定路线已在 Windows + NVIDIA RTX 5070 Ti Laptop GPU 12GB 验证；其他平台或显卡需要单独验证后再写入已支持矩阵。
- 图库响应包含原图 URL、缩略图 URL、PLY/SPZ 大小与版本戳；缺失缩略图会在请求时限量修复。
- React 图库使用虚拟滚动和缩略图加载状态，避免大量模型时滚动卡顿。
- 本地媒体图库通过 `photo_gallery_roots_by_workspace` 配置多个目录，并**按工作目录分桶记忆**（键为归一化后的工作目录路径）；每个目录作为一个相册展示，图片缩略图或视频 poster 可作为封面。切换工作目录时只展示对应桶的相册，切回原目录即可恢复，与模型列表绑定 `{workspace}/outputs` 的行为一致；旧的顶层 `photo_gallery_roots` 会在启动或切换工作目录前自动迁移到对应桶。
- 本地媒体图库启动时只加载认证、设置、模型等必要数据；不得因为配置了大量相册而阻塞应用 boot。相册摘要应在进入图库视图后按需加载。
- 本地媒体图库缓存采用 `{workspace_folder}/.photo-gallery-cache/catalog.json` 保存相册摘要，`albums/<album_id>.json` 保存单相册媒体索引；普通相册列表只读 catalog，普通分页/筛选/排序只读单相册索引，不应触发目录扫描。
- 媒体列表 API 支持 `type=all|photo|video`，仅返回分页元数据、照片缩略图 URL、视频 poster URL 和播放/下载 URL；预览和下载再加载原图或视频流。
- 视频预览使用原生 `<video>` + 自定义控制层，播放 URL 为短期签名的路径式 `/api/video-play/<video_id>/<play_token>/<filename>`；下载仍走 `/api/video-original/<video_id>?download=1` 的正常权限。
- 本地媒体 `media_id` 应能解析出 `album_id`，后端通过相册索引反查相对路径，并再次校验文件仍位于配置 root 内；避免为媒体解析重新引入全局可变查找表。
- 照片缩略图、视频 poster、catalog、每相册索引和批量下载临时 ZIP 写入 `{workspace_folder}/.photo-gallery-cache/`，可删除后重建，不影响原始媒体；删除相册时会清理该相册对应缩略图/poster。
- 照片可单张或多选批量加入现有 3D 生成队列，后端会验证 photo id 属于已配置 root 后复制到 `inputs/`。
- 局域网门禁开启时，模型/媒体列表、预览、下载、导出与 `/files/*` 需要访问码会话；门禁关闭时这些读取恢复开放，但设置、删除、目录管理、重启等仍限制 localhost owner。
- 远程生成/照片转 3D 默认 owner-only；只有门禁开启且 `allow_remote_generation=true` 时，已解锁远程设备才可提交。
- 视频重建 API 与拖入视频上传 API 同样走生成权限矩阵：owner 默认可用；远程仅在门禁开启且允许远程生成时可提交。

## 视频 3DGS 重建

当前稳定路线：

```
本地相册视频 / 拖入视频
  → ffprobe/ffmpeg 元数据与抽帧
  → ns-process-data video / COLMAP 位姿估计
  → ns-train splatfacto 高斯优化
  → ns-export gaussian-splat 导出 PLY
  → focused cleanup（auto/object）
  → 现有 ply_to_spz 压缩
  → outputs/ + 模型图库 + Spark Viewer
```

开发约束：

- 默认输出名使用源视频同名 stem；只有冲突时追加 `-2`、`-3` 等唯一后缀，不把质量档、帧数或 cleanup 作为用户可见后缀。
- `auto` / `object` 模式默认应用 focused cleanup；`environment` 模式保留完整场景。
- 依赖检测使用进程级异步缓存：后端启动后后台预热一次，Settings 可用 `refresh=1` 手动重扫；首页、模型页、普通弹窗和任务创建不得同步重复扫描外部工具。
- Viewer 对视频重建模型的坐标适配应优先保持 camera/OrbitControls 的干净默认状态；当前策略是在模型侧隐藏预乘 orientation 修正视频形态 Y-front 模型，避免相机落入极点导致拖拽 roll。旧 ml-sharp 单图模型不得被该适配改变预览手感。
- Quick Controls 中的相机/模型调试读数可保留，便于后续排查新模型的坐标系、包围盒和交互问题。

## WebXR 支持

React 前端支持 WebXR 双模式：

| 模式 | Session Type | 适用设备 |
|------|-------------|---------|
| **VR** | `immersive-vr` | Quest 3/Pro、Vision Pro |
| **AR Passthrough** | `immersive-ar` | Quest 3/Pro（全彩透视）、Android Chrome |

核心实现在 `hooks/useXR.ts`，采用 Camera Rig 模式 + 高度校准。
