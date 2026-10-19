## ADDED Requirements

### Requirement: 单文件分享 SHALL 独立运行

系统 SHALL 导出包含模型、渲染引擎和样式的单个 HTML，MUST NOT 在运行时依赖应用服务、CDN 或 node_modules；保留现有权限、实际格式回退和安全文件名。

#### Scenario: 完整包导出
- **WHEN** 应用只有已构建前端产物而没有 node_modules
- **THEN** 仍 SHALL 导出可独立打开的分享文件

### Requirement: 分享视角 SHALL 遵守模型约定

分享页 MUST 使用与主查看器一致的归一化方向、默认变换及有效初始相机；MUST NOT 修改嵌入模型的坐标或精度。没有相机的视频模型 SHALL 按包围盒取景，单图保留既有近景语义。

#### Scenario: 视频或编辑结果
- **WHEN** 模型包含有效保存相机、方向与变换
- **THEN** 分享页 SHALL 用这些数据打开，并在重置时恢复

#### Scenario: 缺失相机
- **WHEN** 视频模型没有有效相机
- **THEN** 分享页 SHALL 显示完整模型，并允许重新适应全模型

### Requirement: 独立查看器 SHALL 提供可达交互

分享页 SHALL 保留旋转、平移、缩放、点击聚焦、键盘及触屏移动，提供初始视角、适应全模型、自动环绕、全屏、背景与帮助；中英文 SHALL 同步维护并支持窄屏。默认 MUST NOT 自动降低模型精度。

#### Scenario: 重置及移动
- **WHEN** 用户操作视角后点击初始视角或全模型
- **THEN** 相机 SHALL 恢复对应取景，鼠标和触屏入口保持可见

### Requirement: 导出内容 MUST 安全且失败可恢复

导出 SHALL 仅嵌入白名单预览字段，MUST NOT 包含本机私密路径/门禁信息/原媒体。名称及配置 MUST 安全转义，错误 SHALL 以文本展示并支持重试；异步失败或退出 SHALL 清理资源。

#### Scenario: 非法名称或侧车
- **WHEN** 名称包含 HTML/脚本结束标签或侧车含路径/无效相机
- **THEN** 内容 MUST NOT 执行注入脚本、泄露路径或使用非法相机

#### Scenario: 加载失败
- **WHEN** 数据损坏或 WebGL2 不可用
- **THEN** 查看器 SHALL 展示明确错误及重试入口，不永久停留在进度动画
