## Why

独立分享页虽已使用 Spark 2.0，却绕过主查看器的方向/相机约定，视频重建及编辑后的模型容易从错误位置打开。它还在导出时读取 node_modules，完整便携包与更新安装无法可靠地仅依赖已构建产物。

## What Changes

- 建立随主前端构建的独立分享查看器，导出时嵌入引擎、样式与模型，继续支持离线单 HTML。
- 复用主查看器方向/变换与重建相机规则，优先恢复已保存初始视角；无相机时按模型包围盒取景。
- 保留旋转/平移/缩放、点击聚焦、键盘和触屏移动，增加回到初始视角、适应全模型、自动环绕、全屏与双语帮助。
- 使用现有玻璃态/Token/图标，提供明确加载、错误及重试状态；默认保留完整模型精度，不自动降画质。
- 范围包含生成模型独立分享与导出服务；不扩展未支持的外部资产导出，不改变模型文件或主查看器默认，不包含动画视频导出、公开托管及社交链接服务。

## Capabilities

### New Capabilities
- `standalone-model-sharing`: 离线单文件导出、来源感知取景与独立查看器操作。

### Modified Capabilities
无。

## Impact

涉及 backend/services/export_html.py、templates/share_template.html、frontend/src/share、frontend/vite.config.ts 与 frontend/dist、测试及文档。保留现有导出 API 和权限、格式回退及文件名；复用安装的 Three.js/Spark，不新增依赖或运行时版本要求。
