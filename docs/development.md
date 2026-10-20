# 开发者指南

[English](development.en.md) · [返回 README](../README.md) · [安装与部署](deployment.md)

这里保留架构、源码开发和发布说明；普通安装已包含前端构建产物。参与开发前请阅读仓库[统一规范](../.antigravityrules)及[提交与发布规范](../.agents/skills/commit-and-release/SKILL.md)。

## 🏗️ 技术架构

### 项目结构

```
sharp-gui/
├── 📄 app.py                 # Flask 兼容入口（暴露 app，python app.py 启动）
├── 📁 backend/               # 模块化 Flask 后端
│   ├── 📄 app_factory.py     # create_app()：注册 hooks/routes、挂载 TaskManager
│   ├── 📄 server.py          # 启动服务、HTTPS/LAN bind、重启支持
│   ├── 📄 runtime.py         # 环境变量、verbose 日志、Sharp 命令/设备解析
│   ├── 📄 config.py          # config.json 与 access-control normalize
│   ├── 📄 paths.py           # workspace/inputs/outputs/cache 路径上下文
│   ├── 📁 security/          # LAN 门禁、权限矩阵、request hooks
│   ├── 📁 services/          # 模型资产/照片图库、视频重建、任务队列、自更新、导出、静态文件等服务
│   └── 📁 routes/            # auth/gallery/model_assets/photo_gallery/video_reconstruction/tasks/settings/updates/files/export/frontend
├── 📄 install.sh/bat         # 一键安装脚本
├── 📄 run.sh/bat             # 启动脚本 (支持 --legacy 参数)
├── 📄 run_verbose.sh/bat     # Verbose 启动入口（生成 sharp-gui-verbose.log）
├── 📄 build.sh/bat           # 前端构建脚本
├── 📄 update.sh/bat          # 自动更新脚本
├── 📄 update-manifest.json   # 更新协议、便携运行时 revision 与目标兼容性契约
├── 📄 release.sh/bat         # 发布打包脚本
├── 📁 .sharp-gui-update/     # 本机更新状态、操作锁与诊断（运行时生成）
├── 📁 .sharp-gui-tools/      # 便携包自带工具（含校验过的 MinGit）
├── 📁 tools/                 # 工具脚本
│   ├── 📄 generate_cert.py   # SSL 证书生成工具
│   ├── 📄 download_model.py  # 模型下载工具
│   ├── 📄 detect_cuda.py     # CUDA 版本检测
│   ├── 📄 install_torch.py   # PyTorch + CUDA 智能安装与校验
│   └── 📄 update.py          # 自动更新核心逻辑
├── 📁 frontend/              # React 现代前端 (v1.0.0+)
├── 📁 templates/             # 原始单文件前端 (Legacy)
├── 📁 static/lib/            # Three.js + Gaussian Splats 3D（Legacy 旧前端使用）
├── 📁 ml-sharp/              # (安装后) Apple ML-Sharp 核心
├── 📁 inputs/                # 输入图片
├── 📁 outputs/               # 输出模型 (.ply + .spz)
├── 📁 model-assets/          # 导入模型与资产封面缓存（默认工作区内）
├── 📁 .model-asset-library/  # 模型资产索引和用户编辑信息（默认工作区内）
├── 📁 .video-reconstruction/ # 视频重建 job、上传视频缓存和中间文件（默认工作区内）
└── 📁 .photo-gallery-cache/  # 照片图库索引与缩略图缓存（默认工作区内）
```

### 前端架构 (React)

```
frontend/
├── 📁 src/
│   ├── 📁 api/               # API 客户端 (gallery, modelAssets, photoGallery, tasks, settings, auth)
│   ├── 📁 components/
│   │   ├── 📁 common/        # 通用组件 (Button, Modal, Loading, ImageViewer, ParticleBackground)
│   │   ├── 📁 gallery/       # 图库组件 (GalleryList, GalleryItem)
│   │   ├── 📁 modelAssets/   # 模型资产库组件 (LibraryView, Grid, Toolbar, DetailsPanel)
│   │   ├── 📁 photoGallery/  # 本地照片图库组件 (AlbumList, MasonryGrid, Toolbar)
│   │   ├── 📁 layout/        # 布局组件 (Sidebar, ControlsBar, TaskQueue, Settings, AccessGate)
│   │   └── 📁 viewer/        # 查看器组件 (ViewerCanvas, QuickControls, ViewerRevealEffectsRail, VirtualJoystick, GyroIndicator)
│   ├── 📁 hooks/             # 自定义 Hooks (useViewer, useXR, useGyroscope, useKeyboard, useGalleryVirtualizer)
│   ├── 📁 i18n/              # 国际化 (zh.json, en.json)
│   ├── 📁 store/             # Zustand 状态管理
│   ├── 📁 styles/            # 全局样式 (variables, animations)
│   ├── 📁 types/             # TypeScript 类型定义
│   └── 📁 utils/             # 工具函数
├── 📄 vite.config.ts         # Vite 配置 (代码分割)
└── 📁 dist/                  # 构建产物
```

### 核心技术栈

| 层级         | 技术                                               |
| ------------ | -------------------------------------------------- |
| **前端**     | React 19 + TypeScript + Vite / 原生单文件 (Legacy) |
| **状态管理** | Zustand                                            |
| **国际化**   | i18next + react-i18next                            |
| **样式**     | CSS Modules + Apple Glass Morphism                 |
| **后端**     | Python 3.10+, Flask app factory + Blueprints, TaskManager |
| **AI 引擎**  | Apple ML-Sharp (PyTorch, gsplat)；视频重建使用 Brush + COLMAP/ffmpeg |
| **3D 渲染**  | Three.js + Spark 2.0 (WASM 加速高斯溅射)           |

### 性能优化

| 优化项         | 说明                                                                                |
| -------------- | ----------------------------------------------------------------------------------- |
| **代码分割**   | Vite 按渲染引擎和通用依赖拆分构建产物            |
| **缩略图系统** | 模型资产库复用源媒体缩略图或缓存封面；照片图库按需生成缓存缩略图，预览/下载才读取原图 |
| **资产库浏览** | 模型资产库使用游标式滚动增量加载，网格密度只影响展示列数，不重新扫描模型目录          |
| **视频重建缓存** | 后端启动后异步检测视频重建依赖并缓存结果，Settings 可手动刷新；视频生成结果写入 sidecar 元数据并复用模型图库 |
| **智能轮询**   | 有任务时 2s 轮询，空闲时 10s，节省资源                                              |
| **格式转换**   | 生成后自动转换 SPZ 紧凑模型；分享导出默认嵌入 SPZ，历史 PLY 导出路径保留 Splat 兼容  |
| **内存清理**   | 已完成任务 1 小时后自动从内存中移除                                                 |
| **进度优化**   | 进度条只允许前进，避免视觉跳变                                                      |

---

## 🛠️ 开发环境与发布

### 前端开发

```bash
# 安装依赖
cd frontend
npm install

# 开发模式 (热更新)
npm run dev

# 构建生产版本
npm run build
# 或回到仓库根目录，使用项目脚本
cd ..
./build.sh
```

### 切换前端版本

```bash
./run.sh           # 使用 React 现代版本 (默认)
./run.sh --legacy  # 使用原始单文件版本
./run.sh --verbose # 开启详细诊断日志 (写入 sharp-gui-verbose.log)
```

### 环境变量

后端兼容入口 `app.py` 与 `backend/` 模块支持以下环境变量，普通用户无需设置，开发与排障时可按需使用：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SHARP_FRONTEND_MODE` | `react` | 前端模式：`react`（构建版）或 `legacy`（单文件版）。`run.sh --legacy` 会设为 `legacy`。 |
| `SHARP_DEBUG` | 关闭 | 设为 `1`/`true` 开启 Flask 调试器（向浏览器返回堆栈、启用交互式调试器）。**有安全风险，仅本机排障使用，切勿在局域网/公网开启。** |
| `SHARP_VERBOSE` | 关闭 | 设为 `1`/`true` 开启详细诊断日志文件。`run.sh --verbose` / `run.bat --verbose` 会设置它。 |
| `SHARP_LOG_LEVEL` | `INFO`（verbose 时 `DEBUG`） | 应用日志级别。 |
| `SHARP_HTTP_LOGS` | 关闭 | 设为 `1`/`true` 时输出 Werkzeug HTTP 请求日志；默认关闭，避免缩略图、轮询等请求刷屏。 |
| `SHARP_LOG_FILE` | `sharp-gui-verbose.log` | 详细诊断日志的输出文件路径。 |
| `SHARP_BIND_HOST` | 跟随门禁设置 | 覆盖监听地址。不设时由「局域网门禁」中的局域网绑定开关决定（开 `0.0.0.0` / 关 `127.0.0.1`）。 |
| `SHARP_LAN_IP` | 自动探测 | 启动信息中显示的局域网 IP，`run.sh` 会自动注入。 |
| `SHARP_DEVICE` | 自动选择 | 推理设备：`cpu` / `cuda` / `mps`，留空则自动检测可用设备。 |

> `SHARP_DEBUG` 同时控制调试器、堆栈泄露与源码热重载，三者默认全部关闭。设为 `1` 后全部开启，仅供本机排障使用。（热重载与调试器绑定是因为 Werkzeug reloader 开启时会通过 socket 继承干扰 `/api/restart` 的地址重新绑定。）

### 创建发布包

```bash
# 自动构建并打包
./release.sh v1.0.0

# 输出: sharp-gui-v1.0.0.zip (包含预构建前端)
```

## 🎨 Apple 风格界面设计

采用 Apple Human Interface Guidelines 设计理念：

| 设计元素             | 描述                                                                                            |
| -------------------- | ----------------------------------------------------------------------------------------------- |
| **🪟 Glass Morphism** | 全局 `backdrop-filter: blur(30px)` + 半透明面板，控制栏、Toolbar、Modal 统一玻璃质感           |
| **🔤 SF Pro 字体**    | 苹果系统字体栈，原生级渲染体验                                                                  |
| **✨ 动态粒子背景**   | Canvas 浮动粒子，默认渐显避免首屏闪现                                                           |
| **🎬 流畅过渡动画**   | `cubic-bezier` 调校的交互缓动，遵循 `prefers-reduced-motion`                                    |
| **🌗 深色模式**       | 自适应系统深色偏好                                                                              |
| **🎯 沉浸细节**       | 折叠式底部控制栏、模型加载进度条只前进、骨架屏渐变加载、删除滑出，多选浮动操作条                |
