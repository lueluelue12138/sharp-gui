## Why

同一视频在 Sharp GUI 与 OOOSplat 0.7.0 的中档重建中出现明显的质量和效率差距，且移动相机时的闪烁需要与模型本身的漂浮物分开定位。现有生成资产也缺少可直接查看的重建耗时，难以核对实际生成条件。

## What Changes

- 核对 OOOSplat 0.5.0、0.6.0、0.6.1、0.7.0 发布说明与固定源码，记录普通视频的引擎、训练和相机匹配差异。
- 采用经过验证的视频训练改进，减少不必要的增密，保留真实细节；若更换固定引擎，同步安装校验和便携运行时契约。
- 修正能够复现的预览排序问题，使显示问题不再混淆重建质量。
- 为今后的单图和视频生成保存真实处理耗时、阶段耗时及有用的生成条件，在模型资产库提供本地化展示。
- 包含回归与同素材验证；不扩展全景、补拍、遥测或其它上游功能，不对历史资产虚构耗时，也不自动重建现有模型。

## Capabilities

### New Capabilities
- `model-generation-metadata`: 单图与视频生成的耗时、条件和诊断摘要持久化与展示。

### Modified Capabilities
- `video-3dgs-reconstruction`: 可追踪的视频质量配方和引擎改进、可靠的相机匹配。
- `model-asset-library`: 在资产详情中展示生成摘要并保留编辑派生模型的来源语义。

## Impact

影响 backend/services 的视频、任务、模型资产服务，tools 的引擎安装及必要的便携包契约，frontend/src/hooks、types、modelAssets 组件与双语文本，tests、文档及 frontend/dist。原素材、已有模型文件和 ml-sharp 上游目录保持只读。
