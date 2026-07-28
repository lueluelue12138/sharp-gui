## Why

当前 Viewer 会把模型包围盒形状当作坐标系线索，导致部分 ML-SHARP 单图模型被误判为视频 Y-front 模型并以顶视角打开；与此同时，模型资产库迁移后已有的图片/视频来源元数据没有随当前模型传入 Viewer，视频适配也退化为不可靠的几何猜测。需要恢复来源信息链路，并用确定、可解释的方向策略稳定图片、视频和导入模型的初始预览。

## What Changes

- 为当前模型预览携带明确的来源与方向上下文，使 Viewer 能区分图片重建、视频重建、用户导入、临时预览和经安全识别的旧视频模型。
- 将模型初始方向与包围盒取景解耦：只有明确的视频重建模型使用既有 Y-front 隐藏适配，图片、导入和临时模型不再因包围盒比例被自动旋转；包围盒继续只负责居中、目标点与适配距离。
- 保持 PLY/SPZ 等同一资产不同格式的方向一致，并让用户保存的 Quick Controls 变换稳定地叠加在来源默认方向之上。
- 将调试读数中的“方向判定”和“相机取景模式”分开表达，避免把 `bounds-y-front` 同时当作来源、旋转和居中状态。
- 增加覆盖图片、视频、导入/临时模型、旧视频兼容、格式切换、模型切换和重复重置的回归验证。
- 范围包含 React + Spark 主 Viewer 和模型资产打开链路；不包含自动主方向/PCA/图像语义分析、不新增复杂坐标系编辑器、不修改 ML-SHARP、Legacy 前端或模型文件内容。

## Capabilities

### New Capabilities

- `model-preview-orientation`: 定义多来源模型的显式初始方向策略、确定性未知来源回退、与包围盒取景的职责边界、格式一致性及诊断行为。

### Modified Capabilities

- `model-asset-library`: 打开模型资产时须把来源媒体与方向上下文完整交给 Viewer，而不是只传递通用的 generated/imported 标记。
- `video-3dgs-reconstruction`: 视频 Y-front 适配须由可信视频来源或安全兼容识别触发，不能仅凭包围盒形状应用到其他模型。
- `viewer-transform-quick-controls`: 默认方向、用户变换、逐模型持久化与重置须按明确的合成顺序工作，并保持来源默认方向不被保存的用户变换覆盖或重复累积。

## Impact

- 前端状态与类型：`frontend/src/store/useAppStore.ts`、`frontend/src/types/`。
- 模型打开链路：`frontend/src/App.tsx`、`frontend/src/components/modelAssets/`、仍保留的 gallery 兼容入口。
- Viewer 与调试读数：`frontend/src/hooks/useViewer.ts`、`frontend/src/components/viewer/QuickControls/`、`frontend/src/i18n/en.json`、`frontend/src/i18n/zh.json`。
- 后端继续复用 `backend/services/model_assets.py` 和 `backend/services/model_gallery.py` 已有来源元数据与旧视频安全 backfill；如需补齐兼容查询，仅限现有受控模型 API，不新增外部依赖。
- 测试覆盖前端纯策略/状态行为及现有后端来源元数据契约。`ml-sharp/`、`templates/` 和 `static/lib/` 不受影响。
