# OOOSplat 0.6.0 视频重建复核（2026-10-19）

## 基线与证据

- 之前实际画质对照使用本机 **OOOSplat 0.5.0**，源帧、RGB、相机与统一渲染记录见 [画质复核](video-reconstruction-quality.md)。该记录另注明参考源码 `0e19a3b74122c3bab0103bc2ad3140da0853c74f`；安装版实测与后续源码默认值不可混用。
- 本轮直接比较官方标签：`0.5.0 = f10b1c05350eda8e1a129c2ef58e999e2053f928`，`0.6.0 = c49963e61bf8636409db3af79422f724eec001c6`。原仓库采用 [Apache-2.0](https://github.com/ooolabdev/ooosplat/blob/0.6.0/LICENSE)。本轮借鉴故障分型设计，独立实现，不复制其 Rust 实现。
- [0.5.0 发布说明](https://github.com/ooolabdev/ooosplat/releases/tag/0.5.0) 已包含桥接补帧、显存感知训练、一次 OOM 恢复与补拍；这些不能全算作新版新增。[0.6.0 发布说明](https://github.com/ooolabdev/ooosplat/releases/tag/0.6.0) 记录了后续修订。

## 可借鉴内容与处理结论

| 项目 | 核对结果 | 本轮处理 |
| --- | --- | --- |
| 引擎与增密参数 | 新版改为 OOOBrush 1.0.0、COLMAP 4.2.1，调整快速/均衡高斯上限和增密设置。 | 保留已验证 Brush 0.3.0。引擎升级需另做便携包与同素材画质验证。 |
| 训练 CLI | 新版为 `--total-train-iters`；当前为 `--total-steps`，增密梯度阈值也有显著差异。 | 保留当前配方；不能仅抄参数数值推断细节或速度收益。 |
| 透明素材 | 新版保留 RGB，按 Alpha 0.5 建立黑白 SfM 蒙版，减少重复处理。 | 当前 RGB/JPEG 链路没有完整 Alpha 训练输入；作为独立功能评估。 |
| 二视图轨迹 | 新版要求规划器、质量预设与实际透明遮罩同时满足。当前极致档沿用此前实测配方。 | 会改变几何，需另做同素材对照；本轮不修改。 |
| 桥接与恢复 | 0.5.0 已有；新版继续适配透明素材。当前也有一次补密及初次可用几何回退。 | 保留现有机制；增量追加特征/匹配的提速仍需验证。 |
| 故障诊断 | 上游区分显存与设备丢失；当前把普通 MemoryError 和含糊分配失败也归为显存不足。 | **本轮实施**：区分设备中断、显存、主机 RAM 与普通失败，收紧自动降低预算的条件。 |
| 多任务、MCP、导出与监控 | 新版扩展这些应用功能。 | 超出本轮视频链路小范围修复。 |

引擎和哈希见 [运行时清单](https://github.com/ooolabdev/ooosplat/blob/0.6.0/engines/manifest.json)；CLI 和故障分型见 [Brush 集成](https://github.com/ooolabdev/ooosplat/blob/0.6.0/src-tauri/src/engines/brush.rs)；透明处理见 [FFmpeg 集成](https://github.com/ooolabdev/ooosplat/blob/0.6.0/src-tauri/src/engines/ffmpeg.rs)；二视图和恢复见 [流水线](https://github.com/ooolabdev/ooosplat/blob/0.6.0/src-tauri/src/pipeline/runner.rs)。

## 本轮落地行为

1. Vulkan/DXGI/WGPU 明确设备中断时停止；同一输出含分配失败文字也不自动降预算。
2. 明确 CUDA/HIP/Vulkan 显存不足及 WGPU/PyTorch OutOfMemory 类型继续使用原有最多一次重试。高质量、极致、自定义保留请求训练分辨率和迭代；失败输出不发布。
3. 普通 Python MemoryError、std::bad_alloc、主机内存不足单独提示。仅有 `failed to allocate memory`、`allocation failed` 或 `BufferTooBig` 时保留普通失败与日志尾部，不猜测显存原因。
4. 复用现有任务错误码展示与中英翻译，无新组件、接口字段、依赖或便携运行时升级。

## 验证边界

采用合成 COLMAP 数据、真实格式 PLY/SPZ 和外部进程失败注入验证分类、调用次数、输出隔离与参数。本轮没有重跑用户视频、比较 OOOBrush 1.0 最终画质，也不据此声称画质提升或固定比例提速。

验证结果：视频管线、服务、模型格式、API 合约与安全回归共 **206 项通过**；前端 ESLint 与生产构建通过；OpenSpec 严格校验通过。重试测试覆盖高质量 1920、极致 3840、自定义 3200 长边和原迭代保持；非 OOM 失败仅调用一次训练，留下有效格式 PLY 也不会发布。
