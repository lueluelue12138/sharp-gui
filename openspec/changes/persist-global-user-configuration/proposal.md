## Why

配置目前保存在安装目录，换完整便携包后会找不到工作区与相册设置。需要稳定的用户配置位置和明确的首次迁移/恢复路径，让新安装继续使用原数据。

## What Changes

- 自动创建平台用户目录中的配置，旧安装就地运行时首次导入其 config.json，之后全局配置优先。
- 保留 SHARP_CONFIG_FILE 独立实例/测试隔离；新用户采用不依赖安装目录的默认工作区。
- 原子保存、进程锁与过期写入保护；损坏配置明确报错并保留原文件，避免回落到空配置或关闭门禁。
- 设置显示本机配置位置，提供选择旧安装目录、预览并确认恢复的 owner-only 入口。
- 模型、相册和索引继续位于原工作区；不自动搬移或删除大型数据，不扫描硬盘寻找旧包，不改变运行时依赖。

## Capabilities

### New Capabilities
- `global-user-configuration`: 平台存储、优先级、迁移、恢复、持久化与安全行为。

### Modified Capabilities

无。

## Impact

backend/runtime.py、config.py、新配置存储服务、app_factory、settings 路由与权限分类；前端 Settings、API 与类型、双语文案及构建产物；相关测试、配置说明与本地待办。
