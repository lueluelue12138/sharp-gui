## Why

复核 OOOSplat 0.6.0 时发现其 GPU 故障诊断值得借鉴：当前视频管线把普通 `MemoryError` 和含糊的内存分配失败视为显存不足，可能不必要地降低高斯预算并重试。驱动重置也缺少独立、可理解的提示。

## What Changes

- 区分明确的 GPU 显存不足、设备中断、主机内存不足和普通进程失败，只有明确显存不足可以触发现有一次重试。
- 同步中英提示，保留所有正常重建的质量参数和已有取消、导出隔离规则。
- 记录 0.5.0 到 0.6.0 的源码与运行时差异、当前链路已有能力、可借鉴项及验证边界。
- 不迁移 OOOBrush/COLMAP 运行时，不移植新引擎的增密参数，不调整抽帧、分辨率、迭代或二视图策略，不增加透明素材、MCP、补拍或 UI 重构。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `video-3dgs-reconstruction`: 明确 GPU 失败分类、重试资格与本地化错误行为。

## Impact

- `backend/services/video_reconstruction.py` 的故障分类与现有重试调用。
- `frontend/src/i18n` 中的错误文案及对应 `frontend/dist` 产物。
- `tests/test_video_pipeline.py`、服务和前端合约回归测试。
- `docs/ooosplat-0.6-review.md` 和本地、不纳入版本管理的 `docs/todo.md`。
- 依赖、固定 Brush v0.3.0 与便携运行时修订保持现有版本。
