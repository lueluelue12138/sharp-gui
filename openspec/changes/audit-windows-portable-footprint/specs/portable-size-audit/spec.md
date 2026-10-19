## ADDED Requirements

### Requirement: 工具 SHALL 只读盘点明确输入

工具 SHALL 使用标准库接受明确指定的本地组件或 ZIP，输出 JSON，MUST NOT 下载、删除、修改源文件、导入应用或解压。组件根重叠 MUST 拒绝，目录内链接与特殊文件 MUST 跳过，统计失败 MUST 标记不完整并返回非零退出。

#### Scenario: 本地组件盘点
- **WHEN** 用户指定多个不重叠的 label=path 组件
- **THEN** 工具 SHALL 统计各组件逻辑字节和文件数，跳过链接而保持源文件不变
- **AND** 总数 SHALL 明确仅代表所选组件，不代表历史包或合并后的完整包

#### Scenario: 统计失败
- **WHEN** 文件不可读、消失或输入路径无效
- **THEN** 工具 MUST 返回不完整或明确失败，MUST NOT 将缺失文件按零值成功报告

### Requirement: ZIP 盘点 SHALL 区分压缩和未压缩大小

工具 SHALL 只读取归档目录，报告实际归档字节、压缩 payload 字节、逻辑 payload 字节及分类汇总。MUST NOT 按归档成员路径访问磁盘，也 MUST NOT 暴露成员文件名；异常路径 SHALL 标记为警告。

#### Scenario: 存在恶意路径或高压缩数据
- **WHEN** ZIP 包含 ../ 路径或可高度解压的数据
- **THEN** 工具 SHALL 仅计数元数据并标记异常，MUST NOT 创建文件或读取解压内容

### Requirement: 精简方案 SHALL 保留功能与兼容边界

文档 SHALL 列明上游固定版本、可验证本地数据、压缩口径、图片/视频/分享依赖、候选节省及验收步骤；未实际构建验证的优化 MUST 明确标为计划。打包和运行时本轮 MUST 保持不变。

#### Scenario: 无历史归档
- **WHEN** 原验证归档已被删除
- **THEN** 报告 SHALL 使用当前组件证据并说明限制，MUST NOT 声称已重测旧包或已达成缩包
