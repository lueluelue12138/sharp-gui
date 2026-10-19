## Why

用户观察到 Windows 视频重建完整包约 10 GiB，而 OOOSplat 0.6.0 安装器约 200 MB。需要用真实运行时、上游版本和一致的体积口径定位差异，避免为缩包破坏图片推理、视频重建或离线分享。

## What Changes

- 增加只读体积盘点工具：读取 ZIP 目录或明确指定的本地组件，分别报告未压缩字节、压缩载荷及大文件，不解压、不清理、不下载。
- 输出当前依赖测量、OOOSplat 固定标签的架构/版本对照和分阶段安全精简方案，明确完整包与精简发行版的功能差异。
- 更新本地待办，明确已验证结论及尚需完整包验证的实施项目。
- 范围包含诊断工具、测试与文档；不修改打包器、依赖、引擎和运行时版本，不删除已有文件，不构建占用大量磁盘的新完整包。

## Capabilities

### New Capabilities
- `portable-size-audit`: 无解压只读组件盘点、ZIP 双口径统计和安全方案证据。

### Modified Capabilities
无。

## Impact

tools/audit_portable_size.py、tests/test_portable_size_audit.py、docs/windows-portable-size.md、OpenSpec 与本地 docs/todo.md。无前端、API、安装器或 portableRuntimeRevision 变更。
