## ADDED Requirements

### Requirement: 系统 SHALL 在稳定用户目录加载和保存配置
默认配置 SHALL 独立于安装目录，包含原工作区与相册分桶，且新安装 SHALL 使用既有全局配置。SHARP_CONFIG_FILE MUST 完全覆盖默认位置并保持隔离。新用户默认工作区 SHALL 独立于包目录。

#### Scenario: 换包后读取配置
- **WHEN** 用户已建立全局配置并运行另一解压目录的应用
- **THEN** 系统 SHALL 继续读取同一配置及工作区路径
- **AND** 模型、图库索引和相册 ID SHALL 保持原工作区身份

#### Scenario: 明确指定配置
- **WHEN** 设置 SHARP_CONFIG_FILE
- **THEN** 系统 SHALL 只操作指定文件，MUST NOT 读写全局配置或自动导入包内配置

### Requirement: 首次启动 SHALL 安全迁移当前安装的旧配置
仅在全局配置首次建立时 SHALL 自动导入本安装 config.json，保留未知字段、门禁信息及相册分桶，按旧目录解析相对路径。原文件与媒体 MUST NOT 修改。无旧配置时 SHALL 创建稳定默认配置。

#### Scenario: 包内旧配置存在
- **WHEN** 全局配置尚未建立而本安装有有效旧配置
- **THEN** 系统 SHALL 导入配置并保持其工作区与媒体路径
- **AND** 后续包内旧配置 MUST NOT 覆盖已存在全局配置

### Requirement: 配置持久化 SHALL 防止损坏和过期写入
保存 SHALL 原子完成并串行化并发写入；过期配置 MUST 返回冲突。损坏、已初始化后丢失或不可访问的配置 MUST 明确失败，MUST NOT 默默回落到空设置或关闭门禁。配置和备份 MUST NOT 通过公共文件接口泄露。

#### Scenario: 写入失败或并发更新
- **WHEN** 原子提交失败或另一个写入已改变配置
- **THEN** 系统 SHALL 保留既有有效文件并返回稳定失败或冲突码

#### Scenario: 已有配置损坏或丢失
- **WHEN** 已初始化的配置无法读取
- **THEN** 系统 MUST 拒绝使用空默认值继续服务

### Requirement: owner SHALL 能预览并确认从旧安装恢复配置
系统 SHALL 提供本机 owner-only 恢复入口，预览工作区、相册数及指纹而不返回密钥。确认 SHALL 校验源和目标修订、活动任务及工作区可用性，备份当前配置并要求重启生效；提示 SHALL 同步中英文本。

#### Scenario: 确认恢复
- **WHEN** owner 选择有效旧目录、预览并确认，且配置修订未变、任务已停止、工作区可用
- **THEN** 系统 SHALL 备份当前配置并保存所选配置，沿用原工作区数据

#### Scenario: 恢复期间配置变化或无权限
- **WHEN** 源或目标修订变化、任务活跃、目标不可用，或请求来自非 owner
- **THEN** 系统 SHALL 拒绝恢复且 MUST NOT 修改当前配置或原模型
