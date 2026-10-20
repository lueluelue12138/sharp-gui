## Why

用户已能记录和导出镜头动画，但只能逐镜头观察，不能直观看到相机在模型周围的分布、轨迹和拍摄方向。

## What Changes

- 新增可切换的轨迹总览，从独立观察视角显示模型、编号关键帧、实际插值路径与视锥。
- 播放或定位时同步显示当前相机，支持旋转/缩放观察总览与重新取景。
- 总览仅为辅助预览，不写入模型或导出视频；不包含直接拖动轨迹修改镜头。

## Capabilities

### New Capabilities
- `camera-animation-path-overview`: 镜头动画的空间轨迹与角度可视化。

### Modified Capabilities

无。

## Impact

影响 frontend/src/hooks、utils、components/viewer、i18n 和 dist，复用既有 Three.js / Spark 和 UI，不新增依赖、后端接口或持久化结构。
