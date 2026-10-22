## ADDED Requirements

### Requirement: Readable generation summary
模型资产详情 SHALL 以项目既有样式展示可靠的生成耗时、引擎、质量和关键训练统计，所有新增可见文本 MUST 同时维护中英文。

#### Scenario: Inspect generated model
- **WHEN** 用户打开一个有生成摘要的模型详情
- **THEN** 用户能读取格式化的耗时及已知生成条件，无需解析原始 JSON。

#### Scenario: Inspect edited derivative
- **WHEN** 用户打开保留原始生成摘要的编辑派生模型
- **THEN** 系统明确说明摘要属于原始重建，不把编辑过程标为重新推理。
