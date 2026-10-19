## Context

当前视频完整包同时包含单图 ML-Sharp 和原生 Brush 视频链路。旧验证包已删除，不能把本机源码依赖统计当成历史 ZIP 大小。现有 builder 会复制 base Python、venv、完整 node_modules、固定模型与原生工具；离线 HTML 导出仍读取 node_modules 中的五项运行时资源。

## Goals / Non-Goals

**Goals:** 分清 ZIP 下载大小/载荷/逻辑大小；只读测量，不额外占用大量磁盘；提供可重跑工具和带验收门槛的具体精简计划。

**Non-Goals:** 本轮不改 installer/build/runtime revision、不移除图片推理、不切换引擎、不下载/解压完整包、不声称已缩小已发布包。

## Decisions

1. 用标准库读取 ZIP central directory，既报实际归档字节也报 payload compressed/uncompressed，不解压。替代全量解包会浪费磁盘，并可能受到恶意条目路径影响。
2. 本地盘点必须显式重复指定 label=path，仅遍历这些组件；拒绝作为起点的符号链接/重解析点，跳过内部链接及特殊文件，统计失败使报告标为 incomplete 并以非零退出。替代自动全盘搜索可能遍历用户照片或把不完整值当真。
3. 报告 JSON 输出到 stdout，不自动写文件，不载入 torch/backend 或触发配置、设备探测、下载。目录报告只表示所选源组件逻辑总量，不假装是合并后的完整包；重叠组件拒绝，Python overlay 另行分析。
4. ZIP 按固定公开运行时路径分类，不输出最大文件名；路径异常标记为警告，避免泄露用户文件名或将 unsafe entry 当作正常包。替代扫描内容/压缩比推断依赖是不可靠的。
5. 实际缩包方案分阶段：保留关键能力及许可；先确定依赖闭包/去构建缓存，再改打包器并完成 runtime revision 与完整包发布验证。视频专用或在线按需包作为明确不同的发行形态，不等同完整离线包。

## Risks / Trade-offs

- [没有原始 10 GiB ZIP] → 明确历史数字不能重测，本机数据仅作为当前源组件证据。
- [路径并发变化、权限不足] → 输出 incomplete，非零退出，不宣称完整盘点。
- [压缩大小和逻辑大小混淆] → 字段与表格分开，压缩流抽样不冒充最终 ZIP。
- [删 node_modules 导致分享失败] → 记录实际 five-file 导出依赖闭包及浏览器离线验收。
- [删除 .lib 影响 gsplat JIT] → 不自动裁剪，要求真实推理/编译验证，不能一概删除 *.lib/headers。
- [构建变化影响已发布包更新] → 本轮只交付工具和方案；实施须同批 runtime revision 和新完整包。
