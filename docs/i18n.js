/**
 * Sharp GUI Homepage - Internationalization (i18n)
 *
 * Lightweight i18n system for Chinese/English support:
 * - Auto-detects browser language
 * - Persists preference to localStorage
 * - Supports URL parameter override (?lang=en)
 * - Real-time language switching without page reload
 */

const i18n = {
  zh: {
    // === Meta ===
    "meta.title": "Sharp GUI - 本地化 3D 高斯溅射",
    "meta.description": "Sharp GUI：本地生成图片与视频 3D 高斯模型，编辑、管理并导出动画或独立 HTML。在浏览器中探索你的空间记忆。",

    // === Navbar ===
    "nav.create": "创作",
    "nav.features": "特性",
    "nav.showcase": "演示",
    "nav.architecture": "架构",
    "nav.install": "安装",

    // === Hero Section ===
    "hero.badge": "✨ 自托管 3D 空间相册",
    "hero.title": "你的空间记忆<br>触手可及",
    "hero.subtitle": "打破设备界限，一次部署，全屋访问。无需云端上传，在浏览器中即可生成并漫游令人惊叹的 3D 场景。",
    "hero.cta.start": "快速开始",
    "hero.cta.github": "Star on GitHub",

    // === Workflow Section ===
    "workflow.title": "极简工作流",
    "workflow.subtitle": "从照片或视频，到可探索的 3D 空间",
    "workflow.step1.title": "导入素材",
    "workflow.step1.desc": "拖入照片或视频，也可从本地相册开始；已有模型可直接导入",
    "workflow.step2.title": "本地重建",
    "workflow.step2.desc": "单图使用 Apple SHARP，视频使用 COLMAP + Brush，按素材选择",
    "workflow.step3.title": "探索与创作",
    "workflow.step3.desc": "在浏览器中漫游、编辑模型，进一步导出动画或分享作品",

    // === Photo Gallery Section ===
    "photoGallery.tag": "媒体与模型资产",
    "photoGallery.title": "原片与作品，<br>始终相连。",
    "photoGallery.desc": "把电脑与 NAS 目录设为相册，浏览照片、视频并发起重建。蓝色 3D 标识带你回到已生成的模型；固定的「模型原片」相册汇集作品来源，同一原片的多次生成与编辑副本也能一起查看。",
    "photoGallery.point1": "本地与 NAS 相册",
    "photoGallery.point2": "模型版本关联",
    "photoGallery.point3": "原片预览与下载",
    "photoGallery.point4": "模型资产统一管理",

    // === Video Reconstruction Section ===
    "videoRecon.tag": "视频 3DGS 重建",
    "videoRecon.title": "从视频重建<br>可漫游 3D 场景",
    "videoRecon.desc": "用环绕拍摄的视频重建物品或场景。固定源帧规划、COLMAP 相机配准和 Brush 训练，让连续画面汇成有细节、有层次的静态 3D 模型。",
    "videoRecon.point1.title": "细节优先的质量档",
    "videoRecon.point1.desc": "高质量保留 1920 长边；极致档在 12 GB 预算下保留 3840 长边。",
    "videoRecon.point2.title": "每一步，都看得见",
    "videoRecon.point2.desc": "从抽帧、配准到训练，阶段进度与配准检查清晰呈现，训练中可预览。",
    "videoRecon.point3.title": "让结果继续创作",
    "videoRecon.point3.desc": "输出 PLY / SPZ，进入资产库编辑、导出动画，也能回看原视频。",

    // === Platform Section ===
    "platform.badge": "🌐 无界互联",
    "platform.title": "一次部署，全屋触手可及",
    "platform.subtitle":
      "打破设备隔阂。在 PC 运行服务，手机、平板通过局域网即可流畅访问。<br>响应式设计，为您呈现一致的优雅体验。",

    // === Features Section ===
    "features.title": "核心特性",
    "features.apple.title": "Apple 风格设计",
    "features.apple.desc": "通透的玻璃质感、清晰的层次与自然的动效，深浅主题与中英文界面保持一致。",
    "features.privacy.title": "本地创作，安心访问",
    "features.privacy.desc": "推理与模型保存在本机；局域网访问支持密码门禁，远程设备浏览作品，本机保留管理权限。",
    "features.performance.title": "高性能渲染",
    "features.performance.desc": "Three.js + Spark 2.0 驱动交互预览，支持 PLY、SPZ、SPLAT、RAD，按模型与设备选择渲染效果。",
    "features.control.title": "全模态控制",
    "features.control.desc":
      "不仅支持键盘 WASD 漫游，更支持移动端陀螺仪体感操控，身临其境。",
    "features.joystick.title": "移动端虚拟摇杆",
    "features.joystick.desc":
      "触摸屏设备内置虚拟摇杆，实现如PC端键盘一样的漫游体验。",

    // === Share Section ===
    "share.tag": "独立 HTML 分享",
    "share.title": "一键导出，<br>让作品自由流动",
    "share.desc": "把模型与查看器封装成一个 HTML 文件。无需另建服务，发送文件后即可在支持 WebGL2 的浏览器中离线打开。",
    "share.feature1.title": "一个文件，完整作品",
    "share.feature1.desc": "内嵌模型、查看器与依赖，使用 SPZ 压缩保存模型",
    "share.feature2.title": "打开，就是你选好的角度",
    "share.feature2.desc": "保留初始视角，支持全模型取景、重置与环绕播放",
    "share.feature3.title": "把探索，也交给观众",
    "share.feature3.desc": "背景切换、全屏、双语帮助与移动端触摸控制",

    // === Showcase Section ===
    "showcase.title": "功能演示",
    "showcase.wasd.title": "WASD 漫游",
    "showcase.wasd.desc": "Shift 加速/微调，精准控制视角",
    "showcase.upload.title": "批量处理队列",
    "showcase.upload.desc": "拖拽上传，并支持批量处理和任务中断",
    "showcase.share.title": "一键导出分享",
    "showcase.share.desc": "生成独立 HTML，在支持的浏览器中离线交互查看",

    // === Architecture Section ===
    "arch.badge": "🏗️ 技术架构",
    "arch.title": "简洁而强大",
    "arch.subtitle": "现代化技术栈，为极致体验而生",
    "arch.backend.queue": "异步串行队列",
    "arch.backend.cert": "自签名证书",
    "arch.ai.sharp": "单图推理 · PyTorch",
    "arch.ai.ply": "PLY/SPZ 格式",
    "arch.metric.vr": "VR/AR 支持",

    // === Install Section ===
    "install.title": "即刻开始，留住空间。",
    "install.subtitle": "Windows 原生运行，也支持 macOS 与 Linux 源码安装。",
    "install.download": "前往下载与校验",

    // === Footer ===
    "footer.made": "Made with ❤️ by",
    "footer.disclaimer": "Disclaimer: 本项目生成的模型内容由用户自行负责。",

    // === Language Switcher ===
    "lang.switch": "EN",
    // Creation, library and deployment
    "photoGallery.window": "图库 · 本地媒体",
    "photoGallery.alt": "本地照片与视频图库",
    "photoGallery.guide": "了解原片与模型联动",
    "photoGallery.connection": "原片与模型关联",
    "photoGallery.source": "一份原片",
    "photoGallery.versions": "多个模型版本",
    "videoRecon.guide": "查看重建与环境指南",
    "videoRecon.window": "重建作品 · 三维预览",
    "videoRecon.alt": "视频重建模型的三维预览",
    "videoRecon.route": "视频重建路线",
    "videoRecon.route1": "固定源帧",
    "videoRecon.route2": "相机配准",
    "videoRecon.route3": "高斯训练",
    "videoRecon.note": "视频重建已在 Windows + NVIDIA RTX 5070 Ti Laptop（12 GB）验证。其他平台尚未完成端到端验证；分辨率与耗时取决于素材、档位和设备。",
    "editor.tag": "模型编辑",
    "editor.title": "让主体更干净。<br>让空间更端正。",
    "editor.desc": "在三维视图中修剪多余背景、校准原点与朝向。拖动边界或数值实时预览，从重建结果走向你想保留的作品。",
    "editor.guide": "了解模型编辑",
    "editor.alt": "模型编辑器中的盒形选区、边界拖动与参数面板",
    "editor.point1.title": "选得准，修得净",
    "editor.point1.desc": "矩形、球形与盒形选区，支持相交或完全包含；可删除选中或仅保留主体。",
    "editor.point2.title": "原点与朝向，亲手校准",
    "editor.point2.desc": "模型不动即可设置原点，再绕原点调平；变换写入模型文件，方便继续创作。",
    "editor.point3.title": "保存方式，由你决定",
    "editor.point3.desc": "另存副本或覆盖原模型，保留原片关联与初始视角；支持撤销与重做。",
    "animation.tag": "导出动画",
    "animation.title": "为你的空间，<br>编排一段镜头。",
    "animation.desc": "选好角度，记录关键帧，让镜头沿平滑曲线穿行。轨迹总览同时显示路径、镜头编号与视锥，运动与拍摄方向一目了然。",
    "animation.guide": "了解动画导出",
    "animation.alt": "七个关键帧构成的曲线轨迹、相机视锥与动画导出面板",
    "animation.point1.title": "轨迹与角度，一起看清",
    "animation.point1.desc": "独立总览观察整条路径，播放或拖动时间轴同步查看当前相机，不改动已记录的镜头。",
    "animation.point2.title": "运镜的节奏，自由掌握",
    "animation.point2.desc": "连续平滑、标准缓动、正弦、柔和停靠与匀速，五种曲线适配不同节奏；镜头可保存与载入。",
    "animation.point3.title": "从预览，到高分辨率视频",
    "animation.point3.desc": "横屏或竖屏，1080p / 4K，24 / 30 / 60 fps。逐帧导出无音轨 WebM，编码能力以浏览器与设备检测为准。",
    "features.settings.title": "设置，各归其位",
    "features.settings.desc": "查看器、图库、视频与安全按用途分组。全局配置记住工作区与相册，换新版完整包也能接续使用。",
    "features.update.title": "在界面中管理版本",
    "features.update.desc": "受支持的 Git 安装与受管便携包可在更新中心选择稳定版或最新代码，保留模型、配置与运行环境。",
    "features.library.title": "作品，有序收藏",
    "features.library.desc": "生成、视频和导入模型统一管理，支持排序筛选、详情与元数据查看，以及直接进入编辑。",
    "share.alt": "独立 HTML 分享演示",
    "arch.ai.video": "视频配准与训练",
    "arch.metric.resolution": "动画导出分辨率",
    "arch.metric.framerate": "动画导出帧率",
    "arch.metric.output": "重建与编辑输出",
    "install.portable.title": "Windows 完整便携包",
    "install.portable.desc": "内置运行环境与模型缓存，解压后启动。按显卡选择 RTX 50 或主流 NVIDIA 包；视频重建请选择 RTX 50 视频完整包。",
    "install.portable.note": "Release 提供网盘入口与 SHA256 校验。",
    "install.source.title": "从源码，掌控部署",
    "install.source.desc": "克隆仓库并运行安装脚本。单图推理按设备使用 CUDA、MPS 或 CPU；视频重建另需 COLMAP、Brush 与 FFmpeg。",
    "install.source.guide": "查看完整安装指南",
    "install.commands": "源码安装命令",
    "install.copy.windows": "复制 Windows 安装命令",
    "install.copy.unix": "复制 macOS 与 Linux 安装命令",
    "install.copy.success": "安装命令已复制。",
    "install.copy.error": "无法自动复制，请选择上方命令手动复制。",
    "install.tip": "完整便携包面向 NVIDIA GPU。视频路线当前验证平台为 Windows + RTX 5070 Ti Laptop；请先按安装指南检查设备与依赖。",
    "lang.aria": "Switch to English",
    "singlePhoto.tag": "单张照片 · 空间重建",
    "singlePhoto.title": "熟悉的照片，<br>值得换个角度看。",
    "singlePhoto.desc": "将已有的一张照片，通过 Apple SHARP 转换为可交互的 3D 空间照片。移动视角，看见画面中的远近与层次，让记录过的风景、物品与瞬间多一种打开方式。",
    "singlePhoto.cta": "从你的第一张照片开始",
    "singlePhoto.window": "空间照片 · 视角探索",
    "singlePhoto.alt": "移动观察视角，探索单图生成场景中的空间层次",
    "singlePhoto.point1.title": "已有照片，就能开始",
    "singlePhoto.point1.desc": "风景、物品、生活片段，从本地文件或相册选一张照片即可生成。",
    "singlePhoto.point2.title": "从观看，到探索",
    "singlePhoto.point2.desc": "拖动、缩放或键盘移动视角；手机也能通过触摸与体感观察。",
    "singlePhoto.point3.title": "从相册，直接生成",
    "singlePhoto.point3.desc": "电脑与 NAS 中的照片可直接加入生成队列，支持批量处理与原片回看。",
  },

  en: {
    // === Meta ===
    "meta.title": "Sharp GUI - Local 3D Gaussian Splatting",
    "meta.description": "Sharp GUI turns photos and videos into local 3D Gaussian models. Edit, organize, export animations and share standalone HTML scenes in your browser.",

    // === Navbar ===
    "nav.create": "Create",
    "nav.features": "Features",
    "nav.showcase": "Showcase",
    "nav.architecture": "Architecture",
    "nav.install": "Install",

    // === Hero Section ===
    "hero.badge": "✨ Self-Hosted 3D Spatial Gallery",
    "hero.title": "Your Spatial Memories<br>At Your Fingertips",
    "hero.subtitle": "Break device barriers. Deploy once, access everywhere. Generate and explore stunning 3D scenes right in your browser—no cloud upload needed.",
    "hero.cta.start": "Get Started",
    "hero.cta.github": "Star on GitHub",

    // === Workflow Section ===
    "workflow.title": "Simple Workflow",
    "workflow.subtitle": "From photos or video to a 3D space to explore",
    "workflow.step1.title": "Bring your media",
    "workflow.step1.desc": "Drop photos or a video, start from a local album, or import an existing model.",
    "workflow.step2.title": "Reconstruct locally",
    "workflow.step2.desc": "Apple SHARP for a single photo. COLMAP + Brush for video.",
    "workflow.step3.title": "Explore and create",
    "workflow.step3.desc": "Explore in your browser, edit the model, export an animation or share the scene.",

    // === Photo Gallery Section ===
    "photoGallery.tag": "Media & model library",
    "photoGallery.title": "Your sources.<br>Your creations.<br>Connected.",
    "photoGallery.desc": "Browse photo and video albums from your computer or NAS, then reconstruct in a click. Blue 3D badges lead back to generated models. A pinned Model sources album gathers their media, with repeated generations and edited copies grouped by source.",
    "photoGallery.point1": "Local & NAS albums",
    "photoGallery.point2": "Linked model versions",
    "photoGallery.point3": "Source preview & download",
    "photoGallery.point4": "One model library",

    // === Video Reconstruction Section ===
    "videoRecon.tag": "Video 3DGS reconstruction",
    "videoRecon.title": "Video to 3D,<br>ready to explore.",
    "videoRecon.desc": "Reconstruct an object or scene from a video captured around it. Planned source frames, COLMAP camera registration and Brush training bring those views together in a detailed, static 3D model.",
    "videoRecon.point1.title": "Quality that keeps the detail",
    "videoRecon.point1.desc": "High quality keeps a 1920 px long edge; Ultra keeps 3840 px with a 12 GB budget.",
    "videoRecon.point2.title": "See every stage",
    "videoRecon.point2.desc": "Follow frame extraction, registration checks and training progress, with previews during training.",
    "videoRecon.point3.title": "A starting point for more",
    "videoRecon.point3.desc": "Export PLY / SPZ, edit in your library, make an animation or revisit the original video.",

    // === Platform Section ===
    "platform.badge": "🌐 Seamless Access",
    "platform.title": "Deploy Once, Access Everywhere",
    "platform.subtitle":
      "Break device barriers. Run the server on PC, access from phone or tablet via LAN.<br>Responsive design delivers a consistent elegant experience.",

    // === Features Section ===
    "features.title": "Core Features",
    "features.apple.title": "Apple-Style Design",
    "features.apple.desc": "Translucent surfaces, clear hierarchy and natural motion, with light and dark themes and Chinese and English interfaces.",
    "features.privacy.title": "Local creation. Controlled access.",
    "features.privacy.desc": "Run inference and keep models locally. A password gate controls LAN access, while management stays on the host device.",
    "features.performance.title": "High Performance",
    "features.performance.desc": "Interactive rendering with Three.js and Spark 2.0. Open PLY, SPZ, SPLAT or RAD and choose rendering effects for your scene and device.",
    "features.control.title": "Multi-Modal Control",
    "features.control.desc":
      "Not just WASD keyboard navigation, but also mobile gyroscope for immersive control.",
    "features.joystick.title": "Mobile Virtual Joystick",
    "features.joystick.desc":
      "Built-in virtual joystick for touch devices, PC-like navigation experience.",

    // === Share Section ===
    "share.tag": "Standalone HTML sharing",
    "share.title": "One-Click Export,<br>Let Your Work Flow",
    "share.desc": "Package the model and viewer in one HTML file. Send the file and open it offline in a WebGL2-capable browser, with no separate server.",
    "share.feature1.title": "One file. The full scene.",
    "share.feature1.desc": "Embedded model, viewer and dependencies, with SPZ model compression",
    "share.feature2.title": "Open at the view you chose",
    "share.feature2.desc": "Preserved initial view, full-scene framing, reset and orbit playback",
    "share.feature3.title": "Let others explore",
    "share.feature3.desc": "Backgrounds, fullscreen, bilingual help and mobile touch controls",

    // === Showcase Section ===
    "showcase.title": "Feature Demos",
    "showcase.wasd.title": "WASD Navigation",
    "showcase.wasd.desc": "Shift to speed up/fine-tune, precise camera control",
    "showcase.upload.title": "Batch Processing",
    "showcase.upload.desc":
      "Drag & drop upload, with task queue and cancellation",
    "showcase.share.title": "One-Click Export",
    "showcase.share.desc": "Export a standalone HTML scene for offline interaction in a supported browser.",

    // === Architecture Section ===
    "arch.badge": "🏗️ Architecture",
    "arch.title": "Simple Yet Powerful",
    "arch.subtitle": "Modern tech stack built for the ultimate experience",
    "arch.backend.queue": "Async Serial Queue",
    "arch.backend.cert": "Self-Signed Cert",
    "arch.ai.sharp": "Single-image inference · PyTorch",
    "arch.ai.ply": "PLY/SPZ Format",
    "arch.metric.vr": "VR/AR Support",

    // === Install Section ===
    "install.title": "Start creating. Keep the space.",
    "install.subtitle": "Native on Windows, with source installation on macOS and Linux.",
    "install.download": "Downloads & checksums",

    // === Footer ===
    "footer.made": "Made with ❤️ by",
    "footer.disclaimer":
      "Disclaimer: Users are responsible for the content generated by this project.",

    // === Language Switcher ===
    "lang.switch": "中文",
    // Creation, library and deployment
    "photoGallery.window": "Gallery · Local media",
    "photoGallery.alt": "Local photo and video gallery",
    "photoGallery.guide": "Explore source linking",
    "photoGallery.connection": "Source-to-model connection",
    "photoGallery.source": "One source",
    "photoGallery.versions": "Multiple model versions",
    "videoRecon.guide": "Read the reconstruction guide",
    "videoRecon.window": "Reconstructed model · 3D preview",
    "videoRecon.alt": "Interactive preview of a reconstructed video model",
    "videoRecon.route": "Video reconstruction pipeline",
    "videoRecon.route1": "Source frames",
    "videoRecon.route2": "Camera alignment",
    "videoRecon.route3": "Gaussian training",
    "videoRecon.note": "Video reconstruction is validated on Windows + NVIDIA RTX 5070 Ti Laptop (12 GB). Other platforms have not been validated end to end. Resolution and processing time depend on the source, preset and device.",
    "editor.tag": "Model editor",
    "editor.title": "Refine the subject.<br>Align the space.",
    "editor.desc": "Trim unwanted surroundings and set the origin and orientation in 3D. Drag boundaries or numeric values with live feedback to shape the scene you want to keep.",
    "editor.guide": "Explore model editing",
    "editor.alt": "Model editor with a box selection, draggable boundaries and live parameter controls",
    "editor.point1.title": "Select with precision",
    "editor.point1.desc": "Rectangle, sphere and box selections with intersection or containment rules. Delete the selection or keep only your subject.",
    "editor.point2.title": "Set the origin. Find the level.",
    "editor.point2.desc": "Set the origin without moving the scene, then rotate around it to level the model. Transforms are written into the model file.",
    "editor.point3.title": "Save the way you work",
    "editor.point3.desc": "Save a copy or overwrite the original, preserving source links and the initial view. Undo and redo as you work.",
    "animation.tag": "Export animation",
    "animation.title": "Give your space<br>a cinematic story.",
    "animation.desc": "Choose a view, record a keyframe and let the camera follow a smooth path. See the route, numbered shots and camera frustums together in a dedicated overview.",
    "animation.guide": "Explore animation export",
    "animation.alt": "A curved seven-keyframe path with camera frustums and the animation export panel",
    "animation.point1.title": "See the path and the framing",
    "animation.point1.desc": "Inspect the full path in overview. Play or scrub the timeline to follow the current camera without changing recorded shots.",
    "animation.point2.title": "Choose the rhythm",
    "animation.point2.desc": "Choose continuous smooth motion, standard easing, sine, gentle stops or linear speed. Save and load your shots to keep working.",
    "animation.point3.title": "From preview to a film",
    "animation.point3.desc": "Landscape or portrait, 1080p or 4K, at 24, 30 or 60 fps. Export silent WebM frame by frame, subject to browser and device codec support.",
    "features.settings.title": "Settings, in their place",
    "features.settings.desc": "Viewer, gallery, video and security settings are grouped by purpose. Global configuration remembers your workspace and albums across package installs.",
    "features.update.title": "Manage versions in the app",
    "features.update.desc": "Supported Git installs and managed portable packages offer Stable and Latest channels, preserving models, configuration and the runtime.",
    "features.library.title": "A home for every creation",
    "features.library.desc": "Organize generated, video and imported models together. Sort, filter, inspect metadata and open the editor directly.",
    "share.alt": "Standalone HTML sharing demo",
    "arch.ai.video": "Video alignment & training",
    "arch.metric.resolution": "Animation export resolution",
    "arch.metric.framerate": "Animation export frame rates",
    "arch.metric.output": "Reconstruction & editing output",
    "install.portable.title": "Windows portable packages",
    "install.portable.desc": "Runtime and model cache included. Extract and launch. Choose RTX 50 or mainstream NVIDIA; select the RTX 50 video package for reconstruction.",
    "install.portable.note": "Release notes include download links and SHA256 checksums.",
    "install.source.title": "Deploy from source",
    "install.source.desc": "Clone the repository and run the installer. Single-image inference uses CUDA, MPS or CPU. Video also needs COLMAP, Brush and FFmpeg.",
    "install.source.guide": "Read the installation guide",
    "install.commands": "Source installation commands",
    "install.copy.windows": "Copy Windows installation commands",
    "install.copy.unix": "Copy macOS and Linux installation commands",
    "install.copy.success": "Installation commands copied.",
    "install.copy.error": "Could not copy automatically. Select and copy the commands above.",
    "install.tip": "Portable packages target NVIDIA GPUs. Video is validated on Windows + RTX 5070 Ti Laptop. Check device and dependency requirements in the guide.",
    "lang.aria": "切换为中文",
    "singlePhoto.tag": "Single-photo reconstruction",
    "singlePhoto.title": "A familiar photo.<br>A different point of view.",
    "singlePhoto.desc": "Turn one existing photo into an interactive 3D spatial photo with Apple SHARP. Move your viewpoint to explore depth and rediscover the places, objects and moments you have captured.",
    "singlePhoto.cta": "Start with your first photo",
    "singlePhoto.window": "Spatial photo · Explore the view",
    "singlePhoto.alt": "Exploring depth by moving the viewpoint through a scene generated from a single photo",
    "singlePhoto.point1.title": "Start with what you have",
    "singlePhoto.point1.desc": "A place, an object, a moment. Choose a photo from your files or albums to begin.",
    "singlePhoto.point2.title": "From viewing to exploring",
    "singlePhoto.point2.desc": "Drag, zoom or move with the keyboard. On mobile, explore with touch and gyroscope controls.",
    "singlePhoto.point3.title": "Create straight from an album",
    "singlePhoto.point3.desc": "Queue photos from your local or NAS albums, process them in batches and revisit their source images.",
  },
};

// Current language
let currentLang = "zh";

/**
 * Detect user's preferred language
 * Priority: URL param > localStorage > navigator.language > default (zh)
 */
function detectLanguage() {
  // 1. Check URL parameter
  const urlParams = new URLSearchParams(window.location.search);
  const urlLang = urlParams.get("lang");
  if (urlLang && (urlLang === "en" || urlLang === "zh")) {
    return urlLang;
  }

  // 2. Check localStorage
  const storedLang = localStorage.getItem("sharp-gui-lang");
  if (storedLang && (storedLang === "en" || storedLang === "zh")) {
    return storedLang;
  }

  // 3. Check browser language
  const browserLang = navigator.language || navigator.userLanguage;
  if (browserLang) {
    if (browserLang.startsWith("zh")) {
      return "zh";
    } else {
      return "en";
    }
  }

  // 4. Default to Chinese
  return "zh";
}

/**
 * Get translation by key
 */
function t(key) {
  return i18n[currentLang][key] || i18n["zh"][key] || key;
}

/**
 * Translate all elements with data-i18n attribute
 */
function translatePage() {
  // Update <html lang>
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";

  // Update page title
  document.title = t("meta.title");

  // Update meta description
  const metaDesc = document.querySelector('meta[name="description"]');
  if (metaDesc) {
    metaDesc.content = t("meta.description");
  }

  // Translate all elements with data-i18n
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const key = element.getAttribute("data-i18n");
    const translation = t(key);

    // Check if translation contains HTML
    if (translation.includes("<br>") || translation.includes("<span")) {
      element.innerHTML = translation;
    } else {
      element.textContent = translation;
    }
  });

  // Translate placeholder attributes
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    const key = element.getAttribute("data-i18n-placeholder");
    element.placeholder = t(key);
  });

  // Translate aria-label attributes
  document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
    const key = element.getAttribute("data-i18n-aria");
    element.setAttribute("aria-label", t(key));
  });

  document.querySelectorAll('[data-i18n-alt]').forEach((element) => {
    element.setAttribute('alt', t(element.getAttribute('data-i18n-alt')));
  });

  // Update language switch button text
  const langBtn = document.getElementById("lang-switch-btn");
  if (langBtn) {
    langBtn.textContent = t("lang.switch");
  }
}

/**
 * Set language and translate page
 */
function setLanguage(lang) {
  if (lang !== "zh" && lang !== "en") {
    lang = "zh";
  }

  currentLang = lang;
  localStorage.setItem("sharp-gui-lang", lang);
  translatePage();
}

/**
 * Toggle between Chinese and English
 */
function toggleLanguage() {
  const newLang = currentLang === "zh" ? "en" : "zh";
  setLanguage(newLang);
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  currentLang = detectLanguage();
  translatePage();
});

// Export for global access
window.setLanguage = setLanguage;
window.toggleLanguage = toggleLanguage;
window.t = t;
