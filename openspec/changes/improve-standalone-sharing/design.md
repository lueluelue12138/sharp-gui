## Context

旧模板 1384 行，已嵌入 Spark 2.0，但独立硬编码相机 (0,0,1)、统一 X 翻转与 2 倍缩放，未传递来源方向、viewer_camera、viewer_transform。后端运行时读取 node_modules 的 Three/Spark/Orbit/Pass 拼 importmap，构建产物不能独立支撑导出。官方 Spark SplatMesh 支持 fileBytes 与包围盒，可与项目现有 OrbitControls、WebGL2、PLY/SPZ/SPLAT/RAD 共用。

## Goals / Non-Goals

**Goals:** 离线可分发、方向与主查看器一致、视频重建初始视角可恢复、适合鼠标及触屏操作、类型化可测试、生产包不依赖 node_modules。

**Non-Goals:** 不升级引擎版本、不改训练或模型二进制、不移植编辑器，不扩展外部资产分享、动画导出或公开托管。

## Decisions

1. 采用现有 Three.js + Spark 2.0 的独立 React/TypeScript 查看器，使用现有 Button、lucide 图标、CSS Module 与全局 Token。Why：直接复用方向/相机和 UI，保持相同渲染；备选 SuperSplat/PlayCanvas 会引入第二套坐标和独立依赖，升级未解决当前硬编码问题。
2. Vite 主构建结束时追加独立 IIFE/CSS 构建，输出 frontend/dist/share；后端只读取这两个已构建产物并内嵌。Why：便携包与源码更新均已携带 dist，无需 node_modules；备选运行时转译或 CDN 会破坏可部署性/离线边界。
3. JSON 白名单只传格式、归一化方向/变换/相机及来源类型，名字留在 HTML 转义文本。使用单次模板替换并转义 script 结束标签，禁止注入绝对路径、源视频路径或原片内容。Why：避免侧车私密字段、字符串串联和占位符二次替换；备选直接嵌入完整侧车会泄露路径。
4. 复用 composeViewerModelQuaternion/getReconstructionCameraView 与默认变换；有有效相机用相机，无相机视频按世界包围盒取景，传统单图保留主查看器的默认近景与焦点规则。另提供显式全模型取景。Why：两类来源保持原本语义，导出不改变文件坐标；备选所有模型都自动归零或按名字猜来源会引入跨项目差异。
5. 关闭默认 LoD 构建和自动画质降低，保留完整精度；移动距离跟随当前观察距离与帧间隔。Why：用户重画质，静态分享不应先花时间构建新的 LoD 树；备选固定每帧移动在大场景或高刷新率上体验不一致。已有 RAD 加载按已安装 Spark 能力支持。
6. 保留鼠标/触屏/聚焦/键盘/虚拟移动，新增初始视角、适应全模型、自动环绕、全屏、双语帮助、透明/深/浅背景。异步初始化可取消，清理 renderer/mesh/controls/监听和按键，输入框/按钮焦点不触发漫游。

## Risks / Trade-offs

- [大模型单文件 base64 与解码占用内存] -> 明确进度、分块解码并让出主线程、结束后释放引用，不承诺超出设备显存/内存上限。
- [file:// 与 Blob Worker/WASM 限制] -> 无外部网络依赖，实测 HTTP 和本地文件；浏览器禁用 WebGL2 时给出可读错误和重试。
- [元数据无效/极端包围盒] -> 共用归一化与有限值校验、相机优先、全模型按钮作为显式回退，不自动修改几何。
- [第三方运行时许可] -> 内嵌保留库法律注释和许可证说明，保留 Sharp GUI 项目链接。
- [主构建产物缺失] -> 清晰错误而非回退旧的 node_modules 拼装；源码和独立 dist 同一提交，既有导出权限/文件名/格式响应保留。

## Migration Plan

一次代码更新携带后端、模板和 dist，新导出的 HTML 使用新查看器，已分发旧 HTML 不会改变；可回退同一提交前的完整应用代码，不迁移或改写用户模型。验证格式回退、脚本转义、元数据白名单、方向/相机数值、独立 HTTP/文件加载与移动布局。

## References

- https://sparkjs.dev/docs/splat-mesh/
- https://sparkjs.dev/docs/controls/
- 项目已安装 @sparkjsdev/spark 2.0.0 与 Three.js 0.180.0 源码/类型。

## 2026-10-21 小项补齐

分享模板通过 data URI 内嵌 frontend/dist 中已有的 96px PNG favicon，与应用使用同一品牌资源，避免将大型 raster-in-SVG 再嵌入每个分享文件。缺图标时沿用 share_viewer_unavailable 并在模型转换前退出。自动环绕系数由0.65调整为1.5，继续由 OrbitControls.update(delta) 按时间更新，约40秒一圈；只影响新导出的文件。
