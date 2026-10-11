## Why

图库可以发起重建，但看不到关联模型或任务状态；重复生成与编辑副本需要可靠地归到同一份原片，方便查找与继续编辑。

## What Changes

- 图库卡片和原片预览显示关联模型数量、任务状态及查看入口；多个模型可选择并指定默认模型。
- 固定系统相册“模型原片”汇总有来源的生成模型，按原片去重，支持图片和视频。
- 图片与视频任务记录来源身份，编辑副本继承来源，覆盖保存保留身份；完成、保存、删除自动同步。
- 历史资料采用明确来源、编辑关系和内容校验补齐，不按文件名猜测关联。
- 范围包括来源资料与图库联动；不包含多图重建、训练策略调整、模型坐标修改、源视频额外复制及纯导入模型的虚构原片。

## Capabilities

### New Capabilities
- `model-source-gallery`: 原片身份、关联模型、默认模型、任务标识与系统原片相册。

### Modified Capabilities

无；既有相册和模型库行为在新增能力规格中明确集成。

## Impact

- backend/services: photo_gallery、task_queue、video_reconstruction、model_assets、model_editor 与新增来源服务。
- backend/routes 与 backend/security: 受控来源查询、默认模型写入及既有媒体访问复用。
- frontend/src/components: 图库卡片、相册列表、原片预览与关联模型面板。
- frontend/src/api、types、store、hooks、i18n；工作区模型索引与 sidecar 向后兼容扩展。
- 不增加运行时依赖；前端构建产物与相关文档、测试同步更新。
