## ADDED Requirements

### Requirement: Versioned video quality recipe
系统 SHALL 将视频质量配方绑定到明确的固定训练引擎契约，记录实际采用的配方和资源参数，并使用标准 PLY/SPZ 保存模型效果。

#### Scenario: Balanced video generation
- **WHEN** 用户选择视频中档并开始生成
- **THEN** 系统使用经验证的中档工作分辨率、训练预算和增密限制，生成标准模型和可追踪摘要。

#### Scenario: Changed portable engine
- **WHEN** 目标代码需要与旧完整包不同的固定视频训练引擎
- **THEN** 运行时修订递增且不允许旧包仅通过代码更新获得不完整的新运行环境。

### Requirement: Bounded nonlocal video matching
系统 SHALL 在普通视频顺序匹配中支持有界的跨时间候选匹配，保留原有局部匹配并记录实际执行的策略。

#### Scenario: Video views revisit a scene
- **WHEN** 一个预设视频任务包含相隔较远的已提取画面
- **THEN** 系统使用可验证的图像匹配连接候选画面，不将未经匹配的画面视为已配准，也不修改原视频。
