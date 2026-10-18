## ADDED Requirements

### Requirement: 视频重建 SHALL 依据明确故障类型决定重试

系统 SHALL 区分明确 GPU 显存不足、GPU 设备中断、主机内存不足与普通进程失败。只有明确 GPU 显存不足 SHALL 允许现有的至多一次 Brush 训练重试；所有其它失败 MUST NOT 自动降低分辨率、高斯预算或重新运行训练。新错误提示 SHALL 同步维护中文与英文，并复用现有任务错误展示。

#### Scenario: 明确显存不足
- **WHEN** Brush 非零退出且报告 CUDA/HIP/Vulkan 显存不足或明确 OutOfMemory 错误
- **THEN** 系统 SHALL 保留现有一次重试机制和分离的输出目录
- **AND** 高质量、极致和自定义的请求训练分辨率与迭代次数 SHALL 保持不变

#### Scenario: 设备中断
- **WHEN** 失败输出包含设备丢失、驱动重置或设备移除标记，即使还包含分配失败文字
- **THEN** 系统 SHALL 返回 GPU 设备中断错误并停止训练
- **AND** 系统 MUST NOT 重试、降低预算或发布该失败进程留下的模型

#### Scenario: 主机内存不足
- **WHEN** 失败输出为普通 MemoryError、主机内存不足或 std::bad_alloc，且没有明确 GPU 显存不足原因
- **THEN** 系统 SHALL 提示主机内存不足
- **AND** 系统 MUST NOT 把它解释为显存不足并自动降低高斯预算

#### Scenario: 含糊的分配或缓冲区错误
- **WHEN** 输出只有 failed to allocate memory、allocation failed 或 BufferTooBig，无法确定显存不足
- **THEN** 系统 SHALL 保留普通失败分类与原日志尾部
- **AND** 系统 MUST NOT 自动降低训练质量或触发重试

#### Scenario: 正常成功或取消
- **WHEN** Brush 正常完成或用户取消任务
- **THEN** 系统 SHALL 保持原成功或取消流程，保留原有导出校验与取消后不发布规则
