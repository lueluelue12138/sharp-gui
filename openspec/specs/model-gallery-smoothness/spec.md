# model-gallery-smoothness Specification

## Purpose
TBD - created by archiving change optimize-model-gallery-smoothness. Update Purpose after archive.

## Requirements

### Requirement: Large galleries remain responsive to browse
The system SHALL keep the sidebar model gallery interactive when the gallery contains at least 200 items, and SHALL allow users to continue browsing deeper items without waiting for every offscreen row and thumbnail to be realized up front.

#### Scenario: Initial open with a large gallery
- **WHEN** the user opens the sidebar while the gallery contains at least 200 model entries
- **THEN** the gallery SHALL become scrollable and selectable without requiring all offscreen rows to finish rendering first

#### Scenario: User scrolls deep into a large gallery
- **WHEN** the user rapidly scrolls from the top of a large gallery toward later entries
- **THEN** rows entering the viewport SHALL continue appearing as needed without the sidebar freezing or becoming non-responsive

### Requirement: Gallery browsing context is preserved during refresh and layout-only changes
The system SHALL preserve the user's current gallery browsing context when gallery data is refreshed or when sidebar layout state changes without changing the underlying gallery contents.

#### Scenario: Task completion refreshes the gallery mid-scroll
- **WHEN** the user is browsing the middle of the gallery and a completed task inserts or updates items
- **THEN** the gallery SHALL preserve the user's current viewport anchor instead of resetting the scroll position to the top

#### Scenario: Sidebar visibility changes without gallery content changes
- **WHEN** the user collapses and re-expands the sidebar, or closes and reopens the sidebar on mobile, while gallery contents are unchanged
- **THEN** the gallery SHALL restore the same logical browsing position and visible context

#### Scenario: Unrelated UI state changes occur
- **WHEN** the user changes non-gallery UI state such as opening settings or toggling viewer-only controls while gallery contents remain unchanged
- **THEN** the currently visible gallery rows SHALL remain visually stable and SHALL NOT lose their current thumbnail state

### Requirement: Visible rows always present a stable thumbnail state
The system SHALL present a deterministic visual state for the thumbnail area of every visible gallery row, limited to a loaded thumbnail, a loading placeholder, or an error/fallback placeholder.

#### Scenario: Fast scrolling through thumbnail-heavy content
- **WHEN** the user scrolls quickly through the gallery
- **THEN** each row entering the viewport SHALL show either a thumbnail or a placeholder state, and SHALL NOT present a blank gap where the thumbnail region disappears

#### Scenario: Thumbnail is still loading
- **WHEN** a visible row's thumbnail asset has not completed loading yet
- **THEN** the row SHALL keep a stable placeholder state until the thumbnail is ready

#### Scenario: Row re-enters the viewport
- **WHEN** a row that was already viewed re-enters the viewport during the same browsing session
- **THEN** the row SHALL restore its thumbnail presentation without a visible reset to an empty thumbnail region if the asset is already available

### Requirement: List rows prefer dedicated thumbnail assets
The system MUST use dedicated thumbnail assets for gallery rows when available, and MUST NOT use full-resolution original images as the default row preview path.

#### Scenario: Dedicated thumbnail asset exists
- **WHEN** the gallery item has a valid thumbnail asset
- **THEN** the row SHALL request and render that thumbnail asset as its preview image

#### Scenario: Dedicated thumbnail asset is missing or invalid
- **WHEN** the gallery item has no usable thumbnail asset
- **THEN** the row SHALL render a stable fallback state and the gallery SHALL remain scrollable and selectable without requesting the full-resolution original image as the default row preview

### Requirement: Active selection remains consistent across gallery updates
The system SHALL preserve the active model selection across gallery refreshes whenever the selected model still exists after the refresh.

#### Scenario: Selected model is still present after refresh
- **WHEN** the gallery refreshes and the currently selected model entry still exists
- **THEN** the same model entry SHALL remain selected after the refresh completes

#### Scenario: Selected model was removed
- **WHEN** the gallery refreshes and the currently selected model entry no longer exists
- **THEN** the system SHALL clear the stale active state without leaving an invalid selected row in the gallery

### Requirement: New gallery states are localized
The system MUST provide localized user-visible text for any new gallery loading, fallback, or error states introduced by this capability.

#### Scenario: Language changes after gallery UI is available
- **WHEN** the application language switches between supported locales
- **THEN** all new gallery loading, placeholder, and error messages introduced by this capability SHALL render from locale resources for the selected language

### Requirement: 主模型资产库 SHALL 在大集合下保持响应
系统 SHALL 将既有大模型列表流畅性要求扩展到主模型资产库网格，在至少 200 个模型资产下保持筛选、排序、滚动、选择和详情更新可交互。

#### Scenario: 大模型集合首次进入资产库
- **WHEN** 用户打开包含至少 200 个模型资产的模型资产库
- **THEN** 首屏网格 SHALL 在不等待所有离屏卡片和封面完成渲染的情况下可交互
- **AND** 用户 SHALL 能立即选择可见模型或使用工具栏筛选

#### Scenario: 用户快速滚动模型网格
- **WHEN** 用户快速从模型网格顶部滚动到后续资产
- **THEN** 进入视口的卡片 SHALL 按需呈现封面、加载占位或错误占位
- **AND** 主界面 SHALL NOT 因离屏卡片渲染而冻结

#### Scenario: 多个模型封面同时排队
- **WHEN** 多个可见或刚导入资产需要浏览器离屏封面
- **THEN** 网络处理可以有界并发，但共享 WebGL renderer 的渲染到编码区间 SHALL 串行
- **AND** 完成回调 SHALL 核对资产身份和挂载代次，不能把一个模型封面写到另一个资产

#### Scenario: 查询响应乱序返回
- **WHEN** 用户快速切换筛选或排序且旧请求晚于新请求返回
- **THEN** 只有匹配当前 query signature、generation 和预期 cursor 的响应 SHALL 更新列表状态
- **AND** 旧响应 MUST NOT 覆盖当前列表、游标、loading 或错误状态

#### Scenario: 用户切换筛选和排序
- **WHEN** 用户在大模型集合中切换来源筛选、格式筛选或排序方式
- **THEN** 资产库 SHALL 更新结果集
- **AND** 更新过程 SHALL 保持工具栏和当前可见状态可响应

### Requirement: 模型资产库 SHALL 保留浏览上下文
系统 SHALL 在数据刷新、导入完成、封面更新、布局密度变化或从 viewer 返回时保留模型资产库的当前浏览上下文，除非底层结果集已不再包含相关资产。

#### Scenario: 导入完成后刷新资产库
- **WHEN** 用户正在浏览模型网格中部且新导入任务完成
- **THEN** 资产库 SHALL 将新资产合并到结果集中
- **AND** 当前滚动锚点 SHALL 尽量保持稳定而不是强制回到顶部

#### Scenario: 从 viewer 返回资产库
- **WHEN** 用户从模型资产库打开模型进入 viewer 后返回
- **THEN** 资产库 SHALL 恢复之前的筛选、排序、密度、滚动位置和选中资产

#### Scenario: 选中资产在刷新后仍存在
- **WHEN** 资产库刷新且当前选中资产仍存在
- **THEN** 同一个资产 SHALL 保持选中
- **AND** 详情面板 SHALL 继续显示该资产

#### Scenario: 选中资产已被删除
- **WHEN** 资产库刷新后当前选中资产不再存在
- **THEN** 系统 SHALL 清除过期选中状态
- **AND** 详情面板 SHALL 显示未选择或下一个可用资产状态

### Requirement: 模型资产卡片 SHALL 使用稳定尺寸和缩略图状态
模型资产卡片 SHALL 为封面、文本、徽标和操作区提供稳定尺寸约束，并将封面状态限定为已加载、加载中、失败占位或不可用占位，避免布局跳动和空白闪烁。

#### Scenario: 封面仍在生成或加载
- **WHEN** 可见模型资产的封面尚未生成或加载完成
- **THEN** 卡片 SHALL 显示稳定加载占位
- **AND** 卡片宽高、标题位置和操作按钮位置 SHALL 保持不变

#### Scenario: 封面加载失败
- **WHEN** 模型资产封面请求失败或生成失败
- **THEN** 卡片 SHALL 显示稳定失败占位
- **AND** 用户 SHALL 仍可选择该资产并查看详情

#### Scenario: 切换网格密度
- **WHEN** 用户调整模型网格密度
- **THEN** 卡片 SHALL 根据新密度重新排布
- **AND** 卡片内部文本和徽标 SHALL 不得互相重叠或溢出容器

### Requirement: 模型资产库新增状态 MUST 本地化
系统 MUST 为模型资产库新增的加载、导入、封面生成、空状态、错误、权限和批量选择状态提供中英文 locale 文本。

#### Scenario: 语言切换后查看模型资产库状态
- **WHEN** 应用语言切换到英文或中文
- **THEN** 模型资产库所有新增状态文本 SHALL 使用对应 locale 资源渲染
- **AND** 状态文本 SHALL NOT 以内联硬编码语言残留显示
