## Why

用户能在查看器中手动调整镜头，但不能把多个角度串成可分享的视频。需要一条从记录镜头、预览到导出视频的完整流程。

## What Changes

- 为当前模型增加镜头动画面板，记录、替换、删除、排序关键帧并设置段落时长。
- 提供连续预览、时间定位及逐帧视频导出；支持横屏、竖屏、1080p 与 4K。
- 保持模型文件、坐标、现有预览与编辑流程完整；不包含音轨、模型变形动画或服务端渲染任务。

## Capabilities

### New Capabilities
- `camera-keyframe-animation`: 镜头关键帧、确定性采样、预览与浏览器本地视频导出。

### Modified Capabilities

无。

## Impact

涉及 frontend/src/components/viewer、hooks、utils、i18n 和构建产物；不增加依赖、后端 API 或运行时安装要求。导出能力取决于浏览器的 WebCodecs 编码支持，不支持时明确提示。
