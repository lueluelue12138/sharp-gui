## ADDED Requirements

### Requirement: 设置 SHALL 按用途分组且保持统一风格

界面 SHALL 提供常规、访问与安全、查看器、图库、视频重建、更新中心分组，本机展示全部、远程仅展示权限允许的入口。新导航 SHALL 复用现有控件与设计 Token，支持双语与窄屏，不得产生水平溢出或遮挡底部保存。

#### Scenario: 本机查找设置
- **WHEN** 本机 owner 打开设置并切换分组
- **THEN** 系统 SHALL 仅显示当前分组内容，导航和底部操作保持可达

#### Scenario: 远程访问
- **WHEN** 远程用户打开设置
- **THEN** 系统 MUST NOT 展示 owner-only 图库缓存、配置路径、恢复或更新管理入口
- **AND** 仍 SHALL 保留其查看器、格式偏好和会话功能

### Requirement: 切换分组 SHALL 保留草稿和保存语义

切组 MUST NOT 重置未保存的工作区、视频或其它字段；统一保存 SHALL 提交所有分组的已修改值。即时设置 SHALL 保留既有即时生效语义并给出提示。

#### Scenario: 跨组编辑
- **WHEN** 用户修改视频质量、工作区或其它设置字段后切到其它组再返回
- **THEN** 草稿 SHALL 保持，底部保存 SHALL 一并提交修改

### Requirement: 数据请求 SHALL 按需执行且不覆盖草稿

图库缓存和视频诊断 SHALL 首次访问再读取，诊断刷新 MUST NOT 替换视频草稿。更新 SHALL 首次进入才启动状态读取，已启动的更新轮询 MUST NOT 因切到其它组而停止。

#### Scenario: 只看常规设置
- **WHEN** 打开设置但未进入图库/视频/更新分组
- **THEN** 前端 MUST NOT 因打开弹层发起相应缓存统计、视频诊断或更新状态请求

#### Scenario: 编辑后刷新诊断
- **WHEN** 用户修改视频草稿并刷新依赖诊断
- **THEN** 诊断 SHALL 更新且草稿 MUST 保持用户输入

### Requirement: 导航 SHALL 支持键盘与触控

导航 SHALL 提供稳定的 tab/tabpanel 对应关系、当前状态和可见焦点，支持方向键及 Home/End；窄屏 SHALL 提供全部可见的触控入口。

#### Scenario: 键盘切换
- **WHEN** 用户在分组导航按方向键或 Home/End
- **THEN** 当前分组与焦点 SHALL 一同切换，隐藏内容 MUST NOT 进入普通 Tab 焦点序列

#### Scenario: 优先找到访问与安全
- **WHEN** 用户在桌面或窄屏打开设置
- **THEN** 导航按常规、访问与安全、查看器、图库、视频重建、更新中心排列，权限过滤后访问与安全仍位于第二，键盘导航顺序与显示一致
