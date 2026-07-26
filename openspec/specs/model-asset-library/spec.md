# model-asset-library Specification

## Purpose

Define a unified, secure, responsive, and accessible model asset library for generated and imported models, including indexing, metadata editing, browsing, importing, cover management, and model actions.

## Requirements

### Requirement: Model asset opening SHALL preserve preview orientation context
The model asset service and frontend opening flow SHALL preserve a generated asset's trusted source media classification and normalized preview-orientation hint through list, recent, detail, open, reload, and companion-format selection paths. Imported assets without trusted orientation metadata SHALL be represented as unknown rather than guessed.

#### Scenario: User opens a generated image asset
- **WHEN** an asset is backed by image-generation metadata
- **THEN** the asset opening context SHALL identify the default image orientation
- **AND** the Viewer handoff SHALL retain that context

#### Scenario: User opens a generated video asset
- **WHEN** an asset is backed by video-reconstruction metadata
- **THEN** the asset opening context SHALL identify the video source and Y-front orientation
- **AND** opening from the recent sidebar, library grid, toolbar, or details panel SHALL produce the same context

#### Scenario: User opens an imported asset
- **WHEN** an imported model has no recognized preview-orientation metadata
- **THEN** the asset opening context SHALL mark its orientation as unknown
- **AND** the frontend MUST NOT replace that unknown value with a geometry-derived guess

#### Scenario: Asset exposes companion formats
- **WHEN** one stable asset exposes PLY and SPZ or another supported companion format
- **THEN** every file choice SHALL use the same asset-level source and orientation context
- **AND** changing the preferred open format SHALL preserve the stable asset identity

#### Scenario: Legacy video metadata is backfilled
- **WHEN** the existing conservative legacy-video recovery identifies exactly one trusted source for a generated asset
- **THEN** the refreshed asset summary SHALL expose video source and orientation context
- **AND** ordinary warm pagination MUST NOT repeatedly rescan source media to make that decision

### Requirement: 系统 SHALL 维护统一的模型资产索引
系统 SHALL 将项目生成模型和导入模型表示为统一的模型资产，并为每个资产提供稳定 ID、显示名称、来源类型、主格式、可用模型文件、缩略图状态、用户编辑字段、创建时间、修改时间、文件大小和可打开 URL。

#### Scenario: 现有生成模型进入资产库
- **WHEN** 用户打开模型资产库且 workspace 中已有 `outputs` 生成结果
- **THEN** 系统 SHALL 将可识别的生成模型显示为模型资产
- **AND** 每个资产 SHALL 保留打开查看、下载和删除所需的信息

#### Scenario: 模型存在多个相关格式
- **WHEN** 同一个模型存在 PLY、SPZ、SPLAT 或 RAD 等相关文件
- **THEN** 系统 SHALL 在同一个资产中暴露可用格式列表
- **AND** 系统 SHALL 选择当前 viewer 最适合打开的格式作为默认打开目标

#### Scenario: 资产源文件缺失
- **WHEN** 资产索引中的主模型文件已被外部删除或不可读
- **THEN** 系统 SHALL 将该资产标记为不可用
- **AND** 系统 MUST NOT 返回不存在文件的下载或打开 URL

#### Scenario: 暖索引分页和筛选
- **WHEN** workspace 摘要已建立且用户请求后续游标页、切换筛选或排序
- **THEN** 系统 SHALL 从同一摘要快照计算结果
- **AND** 系统 MUST NOT 再次完整扫描或逐文件 stat `outputs` 目录

#### Scenario: 资产索引损坏
- **WHEN** 模型资产索引 JSON 损坏、schema 非法或无法读取
- **THEN** 系统 SHALL 返回稳定的索引诊断错误并保留原文件
- **AND** 任意导入、编辑、封面或删除写操作 MUST NOT 把损坏索引当作空索引覆盖

#### Scenario: 已索引生成文件在摘要刷新后缺失
- **WHEN** 生成资产已在摘要中但源模型文件在下一次刷新时缺失
- **THEN** 系统 SHALL 保留该资产的稳定身份和用户编辑字段并标记为不可用
- **AND** `files`、`formats` SHALL 为空且打开、下载 URL SHALL 为 null

### Requirement: 模型资产 SHALL 支持用户手动编辑资料
系统 SHALL 允许具备写入权限的用户编辑模型资产的显示名称、标签、备注和手动封面，并将编辑内容保存到资产索引或 sidecar 元数据中，同时保持资产稳定 ID 和源模型文件路径不变。

#### Scenario: 用户编辑显示名称和备注
- **WHEN** 具备写入权限的用户修改模型资产的显示名称、标签或备注
- **THEN** 系统 SHALL 保存这些编辑字段
- **AND** 刷新页面后资产库和详情面板 SHALL 展示更新后的资料

#### Scenario: 用户替换模型封面
- **WHEN** 具备写入权限的用户为模型资产上传手动封面
- **THEN** 系统 SHALL 校验图片类型、大小和目标路径后保存封面
- **AND** 该手动封面 SHALL 优先于系统生成封面展示

#### Scenario: 编辑资产资料不改变源文件
- **WHEN** 用户修改模型资产的显示名称、标签、备注或封面
- **THEN** 系统 MUST 保持资产稳定 ID 不变
- **AND** 系统 MUST NOT 重命名或移动源模型文件

#### Scenario: 无写入权限用户尝试编辑资料
- **WHEN** 未具备写入权限的客户端提交模型资产资料编辑请求
- **THEN** 系统 MUST 拒绝请求
- **AND** 系统 MUST NOT 修改资产索引、sidecar 元数据或封面缓存

### Requirement: 模型资产库主视图 SHALL 高保真呈现示例图布局
前端 SHALL 将模型入口主区域呈现为模型资产库工作台，包含左侧辅助栏、中间模型网格与工具栏、右侧选中详情面板，并尽可能还原用户确认示例图的信息架构、格式徽标、卡片层级和操作布局。视觉主题 SHALL 遵循项目现有 Apple 毛玻璃设计规范、CSS Variables 设计系统和深浅色模式适配，而不是把示例图的固定深色配色作为主题来源。

#### Scenario: 桌面宽屏打开模型入口
- **WHEN** 用户在桌面宽屏视口打开模型入口
- **THEN** 主区域 SHALL 显示模型资产库标题、资产数量、筛选/排序/密度/刷新/导入/选择/打开工具栏
- **AND** 模型网格 SHALL 显示多列模型卡片
- **AND** 右侧 SHALL 显示当前选中模型的预览和详情

#### Scenario: 桌面宽屏视觉参考验收
- **WHEN** 使用包含生成、导入、视频关联和多格式模型的样本数据在桌面宽屏视口验收模型资产库
- **THEN** UI SHALL 保持接近示例图的三栏工作台结构：左侧辅助栏、中间资产网格和右侧详情面板
- **AND** 三栏 SHALL 使用项目既有玻璃态面板、边框、阴影、文本层级和强调色 token 形成清晰层级
- **AND** UI MUST NOT 退化为单列列表、普通表格、营销式首页或照片图库原样套壳

#### Scenario: 深浅色主题视觉验收
- **WHEN** 系统或浏览器处于浅色模式或深色模式
- **THEN** 模型资产库 SHALL 使用项目现有 Light-first + Dark override 策略渲染
- **AND** 文本、边框、玻璃态背景、按钮、选中态和模型缩略图区域 SHALL 在两种主题下保持可读和协调
- **AND** 实现 MUST NOT 只为模型资产库硬编码单一深色主题、OLED 背景或固定示例图配色

#### Scenario: 顶部工具栏视觉参考验收
- **WHEN** 模型资产库处于桌面宽屏布局
- **THEN** 顶部 SHALL 在左侧展示标题和资产总数
- **AND** 来源筛选 SHALL 以分段控件形式展示全部、生成、导入和视频等入口及计数
- **AND** 排序、密度、刷新、导入、选择和打开操作 SHALL 按接近示例图的顺序紧凑排列在工具栏右侧
- **AND** 工具栏控件 SHALL 使用图标或图标加短文本表达，不得挤压、换行错乱或遮挡网格内容

#### Scenario: 模型卡片视觉参考验收
- **WHEN** 模型网格渲染模型资产卡片
- **THEN** 每张卡片 SHALL 保持稳定比例，以上方模型封面为主要视觉区域
- **AND** 卡片 SHALL 展示格式徽标、名称、大小、来源和时间等摘要信息
- **AND** 选中卡片 SHALL 使用项目强调色 token、描边、勾选标识或等价状态接近示例图
- **AND** 查看、下载、导出和删除等快捷操作 SHALL 在悬浮、选中或触摸展开状态中可见且不导致卡片布局跳动

#### Scenario: 详情面板视觉参考验收
- **WHEN** 用户选中一个模型资产
- **THEN** 右侧详情面板 SHALL 在顶部显示较大的模型预览
- **AND** 详情面板 SHALL 显示标题、编辑入口、格式/大小/来源/时间摘要和主要操作
- **AND** 主要操作 SHALL 尽量按查看、下载、导出、分享和删除的顺序呈现；若分享能力暂不可用，UI SHALL 使用禁用态或省略态避免误导
- **AND** 详情内容 SHALL 使用 Details 和 Metadata 或等价标签组织字段

#### Scenario: 滚动增量浏览视觉参考验收
- **WHEN** 模型资产结果超过单屏容量
- **THEN** 网格 SHALL 在接近底部时按后端游标继续加载下一批结果
- **AND** 桌面布局 SHALL NOT 显示独立分页器或每页数量选择
- **AND** 已加载数量、加载中状态、无更多结果状态或加载边界 SHALL 清晰可见

#### Scenario: 没有选中模型
- **WHEN** 模型资产库已加载但用户未选中任何模型
- **THEN** 右侧详情区域 SHALL 显示稳定的未选择状态或默认推荐资产
- **AND** 中间网格 SHALL 保持可浏览和可选择

#### Scenario: 窄屏打开模型入口
- **WHEN** 用户在移动或窄屏视口打开模型入口
- **THEN** 模型资产库 SHALL 重排为无横向溢出的布局
- **AND** 核心操作 SHALL 可通过触摸或键盘访问
- **AND** 操作不得依赖 hover 才能完成

### Requirement: 模型资产库 SHALL 支持筛选、排序、密度和增量浏览
系统 SHALL 支持按来源、格式、标签或媒体关联筛选模型资产，按修改时间、创建时间、名称、大小等常见字段排序，并支持网格密度调整和游标式增量加载。

#### Scenario: 用户按来源筛选
- **WHEN** 用户选择全部、生成、导入或视频来源筛选
- **THEN** 网格 SHALL 只展示匹配筛选条件的模型资产
- **AND** 标题计数和空状态 SHALL 与当前筛选结果一致

#### Scenario: 用户按标签筛选
- **WHEN** 用户选择一个已有模型资产标签
- **THEN** 网格 SHALL 只展示包含该标签的模型资产
- **AND** 清除标签筛选后 SHALL 恢复当前来源和格式筛选下的结果

#### Scenario: 用户改变排序
- **WHEN** 用户选择修改时间、创建时间、名称或大小排序
- **THEN** 系统 SHALL 按请求排序返回或展示模型资产
- **AND** 排序变化 SHALL NOT 要求重新扫描所有模型文件作为普通浏览路径

#### Scenario: 用户调整网格密度
- **WHEN** 用户通过密度控制切换卡片大小或列数
- **THEN** 网格 SHALL 更新布局密度
- **AND** 当前筛选、排序和选中状态 SHALL 保持不变

#### Scenario: 模型数量很多
- **WHEN** 资产库包含至少 200 个模型资产
- **THEN** 首屏 SHALL 在不等待所有资产缩略图完成的情况下变为可交互
- **AND** 后续资产 SHALL 随滚动或翻页增量加载

### Requirement: 模型资产库 SHALL 将 RAD 作为可打开格式展示
模型资产库 SHALL 支持 RAD 资产作为一种可打开模型格式展示，并在首版避免新增 RAD 专属流式状态、分页 chunk、LoD 层级或加载诊断面板。

#### Scenario: 资产包含 RAD 文件
- **WHEN** 模型资产包含 RAD 文件且 viewer 支持 RAD 加载
- **THEN** 资产卡片和详情面板 SHALL 显示 RAD 格式标识
- **AND** 打开该资产时 SHALL 进入现有 viewer 加载流程

#### Scenario: RAD 高级流式元数据不可用
- **WHEN** RAD 资产没有分页、LoD 或流式诊断元数据
- **THEN** 模型资产库 SHALL 仍可展示和打开该资产
- **AND** 详情面板 SHALL NOT 显示空洞或误导性的 RAD 高级状态

### Requirement: 系统 SHALL 支持本机和局域网授权导入模型文件
系统 SHALL 允许 owner 从本机选择、拖拽或批量上传支持的模型文件，并允许满足权限条件的局域网客户端上传模型文件到受控模型资产库。

#### Scenario: 本机用户导入单个模型
- **WHEN** localhost owner 选择一个受支持的 PLY、SPZ、SPLAT 或 RAD 文件导入
- **THEN** 系统 SHALL 将文件复制到受控模型资产目录
- **AND** 系统 SHALL 创建可在资产库中浏览和打开的模型资产

#### Scenario: 用户批量导入模型
- **WHEN** 用户一次上传多个受支持和不受支持的文件
- **THEN** 系统 SHALL 导入受支持且校验通过的模型文件
- **AND** 系统 SHALL 对不受支持或失败的文件返回逐项错误
- **AND** 成功导入的资产 SHALL 不因其他文件失败而回滚

#### Scenario: 批量导入全部失败
- **WHEN** 批量中的所有文件都因校验或保存失败而未导入
- **THEN** 非 2xx 响应 SHALL 同时保留顶层稳定 `error` / `code` 和逐项 `failed[]`
- **AND** 前端 SHALL 按每项稳定 `code` 本地化失败原因

#### Scenario: 并发导入同名模型
- **WHEN** 两个客户端并发导入相同显示名称和扩展名的文件
- **THEN** 系统 SHALL 为它们分配不同的安全物理文件名和稳定资产 ID
- **AND** 删除其中一个资产 MUST NOT 影响另一个

#### Scenario: 导入索引提交失败
- **WHEN** 模型文件已写入临时或受控位置但索引提交失败
- **THEN** 系统 SHALL 回滚本批未提交文件并返回稳定错误
- **AND** 系统 MUST NOT 留下资产库无法管理的孤儿文件

#### Scenario: 主模型页拖入单个模型进行临时预览
- **WHEN** 用户在主模型页的空白画布或侧栏拖入单个受支持模型文件
- **THEN** 系统 SHALL 直接打开该文件的临时预览
- **AND** viewer SHALL 明确提供“加入资产库”操作
- **AND** 系统 SHALL NOT 在用户确认前把临时文件写入资产库

#### Scenario: 模型资产库拖入一个或多个模型
- **WHEN** 用户在模型资产库页面拖入一个或多个受支持模型文件
- **THEN** 系统 SHALL 直接开始批量导入而不是切换到临时预览
- **AND** UI SHALL 显示上传进度、成功数量和逐项失败原因
- **AND** 导入完成后 SHALL 保留当前筛选和滚动上下文并合并新增资产

#### Scenario: 临时预览模型加入资产库
- **WHEN** 用户在临时模型预览中执行“加入资产库”
- **THEN** 系统 SHALL 通过同一受控导入流程持久化该模型
- **AND** 成功后 SHALL 清除临时文件引用并避免刷新后丢失资产

#### Scenario: 局域网客户端导入模型
- **WHEN** 非本机客户端已通过访问控制认证且 owner 明确允许远程生成或导入
- **THEN** 系统 SHALL 允许该客户端上传受支持模型文件
- **AND** 导入结果 SHALL 出现在同一个模型资产库中

#### Scenario: 未授权客户端尝试导入模型
- **WHEN** 未认证远程客户端或未获远程写入权限的客户端提交模型导入请求
- **THEN** 系统 MUST 拒绝请求
- **AND** 系统 MUST NOT 写入模型文件或资产索引

### Requirement: 系统 MUST 安全处理导入文件和资产路径
系统 MUST 校验导入文件扩展名、文件大小、文件名、目标路径和静态文件访问路径，确保模型资产操作不能读取或写入受控资产目录之外的文件。

#### Scenario: 导入文件名包含危险路径
- **WHEN** 上传文件名包含绝对路径、相对穿越片段或平台特殊分隔符
- **THEN** 系统 MUST 净化文件名并写入受控目录
- **AND** 系统 MUST NOT 按客户端提供的原始路径写入文件

#### Scenario: 请求资产文件时尝试路径穿越
- **WHEN** 客户端通过资产下载、缩略图或 `/files/*` URL 尝试访问受控根目录之外的路径
- **THEN** 系统 MUST 拒绝请求
- **AND** 系统 MUST NOT 返回外部文件内容

#### Scenario: 受控根或模型文件通过链接逃逸
- **WHEN** `outputs`、导入目录、封面目录本身或其中模型文件通过 symlink、junction 或 reparse point 指向 workspace 外
- **THEN** 系统 MUST 拒绝列表中的可用 URL、详情、下载、封面和删除操作
- **AND** 系统 MUST NOT 读取、覆盖或删除 workspace 外文件

#### Scenario: 模型文件超出大小限制
- **WHEN** 客户端上传超过配置限制的模型文件或批次
- **THEN** 系统 MUST 拒绝超限文件
- **AND** 响应 SHALL 包含可本地化展示的错误原因

### Requirement: 模型资产 SHALL 提供稳定封面生命周期
系统 SHALL 为模型资产提供稳定封面 URL 或占位状态。生成模型优先复用源图片、视频帧或已有缩略图；导入模型优先由浏览器端离屏渲染生成封面并写入后端缓存；封面不可用时 SHALL 显示稳定占位。

#### Scenario: 生成模型存在源图片缩略图
- **WHEN** 生成模型资产存在可用源图片或视频帧缩略图
- **THEN** 资产卡片 SHALL 使用该缩略图作为封面
- **AND** 系统 SHALL 避免请求全尺寸原图作为普通网格缩略图

#### Scenario: 导入模型需要生成封面
- **WHEN** 导入模型没有可用封面且浏览器能够加载该模型
- **THEN** 前端 SHALL 使用受控离屏渲染生成小尺寸封面
- **AND** 前端 SHALL 将封面提交到后端缓存
- **AND** 后续刷新 SHALL 复用缓存封面

#### Scenario: 封面生成失败
- **WHEN** 模型加载、渲染或封面上传失败
- **THEN** 网格卡片 SHALL 显示格式感知的稳定占位
- **AND** 失败 SHALL NOT 阻止用户打开、下载或删除该模型资产

#### Scenario: 封面正在加载
- **WHEN** 可见模型卡片的封面尚未加载完成
- **THEN** 卡片 SHALL 保持固定封面区域并显示加载占位
- **AND** 网格布局 SHALL NOT 因封面状态变化发生跳动

### Requirement: 模型卡片 SHALL 支持选择、快捷操作和打开查看
模型资产卡片 SHALL 展示封面、名称、格式徽标、来源、时间或大小摘要，并支持单选、选择模式、多选计数、打开 viewer、下载和删除等与权限匹配的操作。

#### Scenario: 用户选择模型卡片
- **WHEN** 用户点击或键盘激活一个模型卡片
- **THEN** 该资产 SHALL 成为当前选中模型
- **AND** 右侧详情面板 SHALL 更新为该资产的信息
- **AND** 选中卡片 SHALL 有清晰视觉状态

#### Scenario: 用户打开模型
- **WHEN** 用户从卡片、工具栏或详情面板执行打开操作
- **THEN** 系统 SHALL 使用该资产默认可打开格式进入现有 viewer 加载流程
- **AND** 资产库的筛选、排序和滚动上下文 SHALL 保留

#### Scenario: 用户进入选择模式
- **WHEN** 用户启用选择模式并勾选多个模型资产
- **THEN** UI SHALL 显示已选数量
- **AND** 批量操作 SHALL 只展示当前权限允许的动作

#### Scenario: 用户批量下载模型资产
- **WHEN** 用户在选择模式中选择一个或多个可用模型资产并执行下载
- **THEN** 系统 SHALL 使用每个资产的首选格式并在不可用时回退到该资产的主要格式
- **AND** 系统 SHALL 通过单个临时 ZIP 下载提供模型文件，避免触发多个浏览器下载
- **AND** 重名文件 SHALL 在压缩包内获得稳定且不覆盖其他文件的名称
- **AND** 不可用资产 SHALL 被跳过并以本地化结果反馈成功与失败数量

#### Scenario: owner 批量删除模型资产
- **WHEN** owner 选择一个或多个模型资产并执行删除
- **THEN** UI SHALL 在一次确认中明确展示待删除数量
- **AND** 系统 SHALL 删除确认范围内的资产并返回逐项成功或失败结果
- **AND** UI SHALL 从当前列表和选择集合移除成功项，保留失败项并显示本地化反馈

#### Scenario: 非 owner 使用选择模式
- **WHEN** 已认证但非 owner 的用户选择模型资产
- **THEN** 批量下载 SHALL 在资产可读取时可用
- **AND** 批量删除 SHALL 不显示且后端删除端点 SHALL 继续要求 owner 权限

#### Scenario: 用户清除批量选择
- **WHEN** 用户通过批量操作条的关闭控件清除选择
- **THEN** 系统 SHALL 清空已选资产并退出选择模式
- **AND** 批量操作条 SHALL 消失且不改变当前筛选、排序和滚动上下文

### Requirement: 详情面板 SHALL 展示模型元数据和操作
模型资产库 SHALL 为当前选中资产展示较大封面、名称、主要操作、文件详情、格式、来源、创建/修改时间、大小、点数、包围盒、关联源媒体和可用元数据标签页。

#### Scenario: 选中资产包含完整元数据
- **WHEN** 当前选中模型资产包含点数、包围盒、源媒体或格式详情
- **THEN** 详情面板 SHALL 以可扫描字段展示这些信息
- **AND** 字段标签 SHALL 使用本地化文本

#### Scenario: 选中资产缺少部分元数据
- **WHEN** 当前选中模型资产缺少点数、包围盒或源媒体信息
- **THEN** 详情面板 SHALL 显示未知或不可用状态
- **AND** 缺失字段 SHALL NOT 导致面板崩溃

#### Scenario: 用户从详情面板执行操作
- **WHEN** 用户在详情面板点击打开、下载、导出或删除
- **THEN** 系统 SHALL 对当前选中资产执行对应动作
- **AND** 操作成功或失败状态 SHALL 以本地化反馈呈现

#### Scenario: 导入资产或临时预览显示导出操作
- **WHEN** 当前模型来源为导入资产或临时 Blob 且没有专用受控导出实现
- **THEN** UI SHALL 省略或禁用旧导出与分享操作并解释原因
- **AND** UI MUST NOT 把导入 asset id 或 Blob id 发送到旧 `/api/export/<id>`

#### Scenario: 远程只读用户查看资产操作
- **WHEN** 已认证远程用户没有模型资产写入或 owner 删除权限
- **THEN** 导入、资料、封面和删除控件 SHALL 按实际能力隐藏或禁用
- **AND** 前端 SHALL NOT 依赖必然失败的 403 请求作为正常交互路径

### Requirement: 模型资产库 MUST 保持中英文文本同步和可访问
所有新增模型资产库用户可见文本 MUST 同时维护英文和中文 locale 资源；新增控件 SHALL 支持键盘导航、可见焦点、语义标签和非 hover 的触摸操作路径。

#### Scenario: 用户切换语言
- **WHEN** 应用语言在英文和中文之间切换
- **THEN** 模型资产库标题、筛选、排序、按钮、空状态、错误、权限提示、字段标签和工具提示 SHALL 从当前 locale 渲染

#### Scenario: 键盘用户浏览资产库
- **WHEN** 用户只使用键盘导航模型卡片、工具栏和详情面板操作
- **THEN** 焦点状态 SHALL 可见
- **AND** 每个可操作控件 SHALL 暴露清晰语义标签

#### Scenario: 触摸设备使用资产库
- **WHEN** 用户在触摸设备上浏览、选择或打开模型资产
- **THEN** 核心操作 SHALL 可通过可见控件完成
- **AND** UI MUST NOT 要求 hover 才能发现唯一操作入口
