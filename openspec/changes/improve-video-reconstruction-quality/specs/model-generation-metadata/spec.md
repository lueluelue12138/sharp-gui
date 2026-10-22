## ADDED Requirements

### Requirement: Record actual generation work
系统 SHALL 为成功生成的单图和视频模型保存版本化生成摘要，包含真实处理耗时和已知引擎信息；排队时间 MUST 不计入重建耗时，未测得的数据 MUST 不伪造。

#### Scenario: New image generation
- **WHEN** 单图推理和结果后处理成功完成
- **THEN** 系统保存实际总耗时、可用阶段耗时和引擎信息，重启后仍可读取。

#### Scenario: New video reconstruction
- **WHEN** 视频配准、训练和结果发布成功完成
- **THEN** 系统保存总耗时、实际阶段耗时、训练配方、输入规格、配准情况及可用的点数。

#### Scenario: Historical asset
- **WHEN** 资产没有可靠的生成耗时记录
- **THEN** 系统不从文件时间推算或把缺失值作为零秒。
