# video-3dgs-reconstruction Specification

## Purpose
Define the local-video-to-3DGS reconstruction workflow, including task creation, runtime pipeline behavior, dependency diagnostics, output compatibility, and UI requirements.

## Requirements

### Requirement: Video preview orientation SHALL require verified video provenance
The video reconstruction pipeline SHALL record a normalized Y-front preview-orientation hint with successful video model metadata, and Viewer SHALL apply video orientation only when an explicit hint, trusted video source metadata, or the existing conservative legacy recovery verifies that provenance.

#### Scenario: New video reconstruction completes
- **WHEN** a video reconstruction successfully produces a model
- **THEN** its sidecar and model-asset projection SHALL identify the model as video-derived
- **AND** they SHALL expose the Y-front preview-orientation hint used by Viewer

#### Scenario: Verified video model opens in Viewer
- **WHEN** a verified video model is opened from any model-asset entry point
- **THEN** Viewer SHALL retain the existing hidden model-side Y-front correction
- **AND** camera reset MUST NOT move the initial orbit to a polar singularity to reproduce the front view

#### Scenario: Legacy video has no explicit orientation hint
- **WHEN** a legacy generated model lacks an orientation hint but the existing safe backfill verifies a unique source video
- **THEN** the system SHALL treat it as a video model for preview orientation

#### Scenario: Legacy source remains ambiguous
- **WHEN** a generated model has neither trusted image/video metadata nor a unique safe legacy match
- **THEN** the system MUST use the unknown/default preview policy
- **AND** bounding-box shape MUST NOT promote it to video orientation

#### Scenario: Image bounds resemble a video model
- **WHEN** an image-generated model satisfies any former video-like AABB depth ratio
- **THEN** Viewer MUST preserve image orientation
- **AND** video compatibility behavior MUST NOT alter the image model's initial preview

### Requirement: 系统 SHALL 从本地视频创建重建任务
系统 SHALL 允许具备生成权限的用户从已配置本地相册中的受支持视频创建静态 3DGS 重建任务，并且不得向前端暴露源视频的绝对文件系统路径。

#### Scenario: 用户从视频创建重建任务
- **WHEN** 具备生成权限的用户提交一个受支持的本地相册视频用于 3D 重建
- **THEN** 系统 SHALL 为该视频创建一个重建任务
- **AND** 该任务 SHALL 出现在现有任务队列响应中
- **AND** 响应 SHALL 使用稳定媒体 ID 或安全文件名引用来源
- **AND** 响应 MUST NOT 暴露源视频的绝对文件系统路径

#### Scenario: 用户拖入单个视频文件创建重建任务
- **WHEN** 具备生成权限的用户在模型视图、模型列表或生成新模型入口拖入一个受支持视频文件
- **THEN** UI SHALL 打开同一套视频生成 3D 弹窗，让用户在提交前确认模式、质量、引擎和输出名称
- **AND** 用户提交弹窗后，系统 SHALL 将视频保存到受控工作区缓存并创建视频重建任务
- **AND** 默认输出名称 SHALL 使用源视频同名 stem，不自动追加质量档或清理策略后缀
- **AND** 响应 MUST NOT 暴露源视频缓存的绝对文件系统路径

#### Scenario: 用户拖入图片文件创建模型
- **WHEN** 用户在模型视图、模型列表或生成新模型入口拖入一个或多个受支持图片文件
- **THEN** 系统 SHALL 沿用现有 SHARP 图片生成任务
- **AND** 系统 MUST NOT 将图片错误提交到视频重建流程

#### Scenario: 用户混合拖入视频和其他文件
- **WHEN** 用户一次拖入多个视频，或同时拖入视频和图片/模型文件
- **THEN** UI SHALL 给出明确提示
- **AND** 系统 MUST NOT 静默忽略部分文件或创建含糊任务

#### Scenario: 用户提交照片或未知媒体
- **WHEN** 用户向视频重建入口提交照片、未知媒体 ID 或非视频媒体
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 SHALL 不创建任务
- **AND** 前端 SHALL 显示本地化错误原因

#### Scenario: 源视频不再存在
- **WHEN** 用户提交的视频 ID 曾经存在但源文件已被移动、删除或相册索引过期
- **THEN** 系统 MUST 拒绝创建重建任务
- **AND** 系统 SHALL 返回可理解的源文件不可用错误
- **AND** 系统 MUST NOT 尝试访问相册根目录之外的路径

#### Scenario: 远程用户没有生成权限
- **WHEN** 未获得远程生成权限的远程客户端尝试创建视频重建任务
- **THEN** 系统 MUST 拒绝请求
- **AND** 系统 MUST NOT 创建任务或复制媒体到工作区
- **AND** UI SHALL 以和现有生成权限一致的方式提示权限不足

### Requirement: 视频重建任务 SHALL 支持模式、预设质量和自定义参数
系统 SHALL 在任务创建前支持 `自动`、`物品`、`环境` 三种重建模式，以及 `快速预览`、`高质量`、`极致` 三种默认质量预设，并提供 `自定义` 单次任务参数入口。

#### Scenario: 用户接受默认选项
- **WHEN** 用户不修改重建弹窗中的模式和质量
- **THEN** 任务 SHALL 使用 `自动` 模式
- **AND** 任务 SHALL 使用设置中配置的默认质量档位
- **AND** 弹窗 SHALL 在提交前显示即将使用的默认值

#### Scenario: 用户选择物品模式
- **WHEN** 用户选择 `物品` 模式并提交任务
- **THEN** 任务 SHALL 记录为 object-centric 重建
- **AND** UI SHALL 在提交前显示所选模式
- **AND** 任务阶段或详情 SHALL 能表达是否使用了前景处理或降级路径

#### Scenario: 用户选择环境模式
- **WHEN** 用户选择 `环境` 模式并提交任务
- **THEN** 任务 SHALL 记录为 environment-centric 重建
- **AND** UI SHALL 在提交前显示所选模式

#### Scenario: 请求包含非法选项
- **WHEN** 请求中包含不受支持的模式、质量档位、引擎策略、自定义参数或帧预算
- **THEN** 系统 MUST 拒绝请求
- **AND** 任务队列 SHALL 保持不变
- **AND** 前端 SHALL 显示本地化校验错误

#### Scenario: 用户选择自定义参数
- **WHEN** 用户选择 `自定义` 并提交目标帧数、训练迭代、输入下采样、COLMAP 匹配方式和图像缓存
- **THEN** 任务 SHALL 记录该组自定义参数
- **AND** 管线 SHALL 按该组参数构造抽帧、几何和训练命令
- **AND** UI SHALL 在提交前解释这些参数对覆盖范围、细节、耗时和显存的影响
- **AND** 系统 SHALL 拒绝明显危险的组合，例如过高帧数搭配完整匹配导致匹配对数平方级增长

### Requirement: 重建管线 SHALL 生成现有模型图库兼容的产物
成功的视频重建任务 SHALL 在现有模型输出目录生成 `.ply` 模型，并尽可能生成同名 `.spz` 紧凑模型，使现有模型图库、查看器、下载和导出流程可以复用。

#### Scenario: 视频重建成功完成
- **WHEN** 视频重建任务成功完成
- **THEN** workspace `outputs/` 目录 SHALL 存在一个 `.ply` 模型
- **AND** 系统 SHALL 尝试生成同名 `.spz` 模型
- **AND** 生成的模型 SHALL 在模型图库刷新后可见
- **AND** 模型图库条目 SHALL 尽量使用源视频封面帧作为缩略图
- **AND** 模型图库条目 SHALL 提供原视频预览入口
- **AND** 任务 SHALL 进入 completed 状态

#### Scenario: 用户删除拖入视频生成的模型
- **WHEN** 用户删除由拖入视频文件生成的模型
- **THEN** 系统 SHALL 删除该模型的 `.ply/.spz`、缩略图和 sidecar 元数据
- **AND** 系统 SHALL 删除受控上传缓存中的源视频副本
- **AND** 系统 MUST NOT 删除本地相册中的原始视频文件

#### Scenario: SPZ 压缩失败但 PLY 已生成
- **WHEN** 视频重建已成功生成 `.ply`，但 `.spz` 压缩失败
- **THEN** 任务 SHALL 记录清晰的 SPZ 压缩失败详情
- **AND** `.ply` 产物 SHALL 保留
- **AND** 模型图库 SHALL 仍可显示和打开 `.ply` 模型

#### Scenario: 用户打开生成结果
- **WHEN** 用户从模型图库选择视频重建生成的模型
- **THEN** 现有 Spark Viewer SHALL 按当前模型源选择规则加载该模型
- **AND** 用户 SHALL 能继续使用现有查看、下载和导出操作

#### Scenario: 视频重建模型坐标偏离默认视轴
- **WHEN** 用户打开的视频重建模型整体中心明显偏离 Viewer 默认相机视轴
- **THEN** Viewer SHALL 基于 Spark 模型包围盒重置初始相机位置和 OrbitControls 目标点
- **AND** 初始画面 SHALL 朝向模型主体而不是空区域或天空
- **AND** 左右拖拽 SHALL 围绕主体中心旋转，而不是因目标点错误表现为倾斜滚转

#### Scenario: 视频重建模型需要坐标系朝向适配
- **WHEN** 视频重建模型的主体正面落在 Viewer 默认轨道的侧向轴上
- **THEN** Viewer SHALL 优先通过模型侧隐藏 orientation 适配模型朝向
- **AND** camera 与 OrbitControls SHOULD 保持默认 `Y-up`、`-Z forward` 和接近水平轨道的初始状态
- **AND** 系统 MUST NOT 通过把初始相机极角推到轨道极点或切换异常 camera up 向量来伪造正面画面

#### Scenario: 已居中的现有模型保持原有预览行为
- **WHEN** 用户打开已围绕默认视轴居中的现有 ml-sharp 单图模型，或 Viewer 无法安全取得模型包围盒
- **THEN** Viewer SHALL 保持原有相机 reset 行为
- **AND** 系统 SHALL NOT 为修复视频重建模型而改变旧模型的默认预览手感

#### Scenario: 输出名称与已有模型冲突
- **WHEN** 用户指定的输出名称或从视频派生的输出名称与已有模型冲突
- **THEN** 系统 SHALL 自动生成安全唯一的输出名称
- **AND** 系统 MUST NOT 覆盖已有 `.ply` 或 `.spz` 文件

#### Scenario: 输出名称包含特殊字符
- **WHEN** 视频文件名或用户输入的输出名称包含空格、中文或不适合作为文件名的字符
- **THEN** 系统 SHALL 生成安全且可识别的输出文件名
- **AND** 任务和图库 SHALL 显示可读名称

#### Scenario: 自动或物品模式输出需要主体聚焦清理
- **WHEN** `自动` 或 `物品` 模式的视频重建成功导出 Gaussian Splat PLY
- **THEN** 系统 SHALL 尝试应用主体聚焦后处理以移除远离主体、透明度低或尺度异常的游离 splat
- **AND** 系统 SHALL 保留清理统计或降级原因，便于解释输出体积和 splat 数变化
- **AND** 如果清理会移除过多几何，系统 SHALL 保留原始导出而不是生成空洞模型

#### Scenario: 环境模式输出需要保留完整场景
- **WHEN** 用户选择 `环境` 模式并完成视频重建
- **THEN** 系统 SHALL 避免应用主体聚焦裁剪，优先保留完整空间场景

#### Scenario: 物品模式按相机环绕几何聚焦主体
- **WHEN** 用户显式选择 `物品` 模式且素材为环绕主体拍摄
- **THEN** 系统 SHALL 在统计清理基础上，额外依据相机环绕几何估计主体中心与范围，裁掉主体范围外的环境 splat
- **AND** `自动` 与 `环境` 模式 MUST NOT 应用该主体范围裁剪，避免误裁完整场景
- **AND** 当相机几何不足以可靠估计主体范围，或裁剪会移除过多几何时，系统 SHALL 跳过该裁剪并回退到统计清理结果

### Requirement: 任务队列 SHALL 展示视频重建阶段
任务队列 SHALL 为长时间运行的视频重建任务暴露清晰阶段，使用户无需阅读日志即可理解当前进度。

#### Scenario: 任务正在准备和抽帧
- **WHEN** 视频重建任务正在读取视频、抽取关键帧或过滤模糊帧
- **THEN** 任务 SHALL 报告抽帧或帧准备阶段
- **AND** 任务 SHALL 保持可取消

#### Scenario: 任务正在估计几何
- **WHEN** 视频重建任务正在估计相机位姿、稀疏点云、深度或初始化几何
- **THEN** 任务 SHALL 报告几何或位姿估计阶段

#### Scenario: 任务正在处理物品前景
- **WHEN** 物品模式任务正在生成或应用前景 mask
- **THEN** 任务 SHALL 报告前景处理阶段
- **AND** 如果前景依赖不可用导致降级，任务 SHALL 记录降级说明

#### Scenario: 任务正在优化高斯
- **WHEN** 视频重建任务正在训练或优化 Gaussian Splats
- **THEN** 任务 SHALL 报告高斯优化阶段
- **AND** 任务 SHALL 提供可显示的进度或阶段状态

#### Scenario: 用户查看任务已用时间与阶段耗时
- **WHEN** 视频重建任务正在处理
- **THEN** 任务卡片 SHALL 实时显示该任务已处理的时长
- **AND** 后端日志 SHALL 在阶段切换和任务结束时记录各阶段耗时与总耗时
- **AND** 当某步骤长时间无输出时，后端 SHALL 周期性记录仍在运行的提示，避免被误判为卡死
- **AND** 计时信息 MUST NOT 暴露源视频或工作区的绝对文件系统路径

#### Scenario: 任务正在导出和压缩
- **WHEN** 视频重建任务正在写出 `.ply` 或压缩 `.spz`
- **THEN** 任务 SHALL 报告导出或压缩阶段

#### Scenario: 用户取消重建任务
- **WHEN** 用户取消 pending 或 running 的视频重建任务
- **THEN** 系统 SHALL 在存在运行中子进程时请求终止该进程
- **AND** 系统 SHALL 终止该子进程派生的整棵进程树，避免遗留进程继续占用 GPU 显存
- **AND** 任务 SHALL 到达 cancelled 状态
- **AND** 临时文件清理 SHALL 遵守保留中间文件设置

#### Scenario: 用户查看训练实时进度
- **WHEN** 视频重建任务进入高斯优化阶段且底层训练框架提供实时预览服务
- **THEN** 系统 SHALL 在任务详情中暴露安全的实时进度入口（如本地训练查看器链接）
- **AND** 系统 SHALL 在不降低当前日志级别的前提下记录该入口
- **AND** 进度 SHALL 在优化阶段随训练推进更新，而不是长时间停在固定值
- **AND** 当其他设备通过局域网访问发起或查看任务时，实时进度入口 SHALL 指向运行重建的主机地址，而不是访问者本机
- **AND** 实时进度入口地址 MUST NOT 暴露源视频或工作区的绝对文件系统路径
- **AND** 当实时预览服务启动失败但训练本身仍可不依赖该服务运行时，系统 SHALL 自动禁用实时预览并重试训练，而不是让任务直接失败

### Requirement: 系统 SHALL 检测重建依赖可用性
系统 SHALL 在用户运行视频重建前暴露必需依赖的可用状态，并在依赖缺失时给出明确提示。

#### Scenario: 必需依赖缺失
- **WHEN** 视频抽帧、稳定重建或导出所需的必需依赖不可用
- **THEN** UI SHALL 显示视频重建不可用或处于降级状态
- **AND** 任务创建 SHALL 以明确依赖错误失败，而不是产生含糊的进程失败

#### Scenario: 用户查看设置页诊断
- **WHEN** 用户打开设置页的视频重建诊断区域
- **THEN** 系统 SHALL 显示基础视频工具和稳定路线依赖的可用状态
- **AND** 诊断信息 SHALL 使用本地化文案
- **AND** 诊断信息 MUST NOT 显示未处理的 Python 堆栈作为主要用户提示

#### Scenario: 应用启动后异步预热依赖状态
- **WHEN** 后端应用进程启动
- **THEN** 系统 SHALL 在后台异步启动视频重建依赖检测
- **AND** 首页、模型图库和普通设置读取 MUST NOT 等待该检测完成才返回

#### Scenario: 依赖状态已有缓存
- **WHEN** 视频重建依赖状态已经在当前后端进程中完成检测
- **THEN** 状态 API SHALL 返回缓存结果
- **AND** 打开视频重建弹窗或创建任务 MUST NOT 为同一请求同步重复扫描外部重建工具

#### Scenario: 依赖状态仍在检查中
- **WHEN** 用户在启动后的依赖检测尚未完成时打开视频重建弹窗或提交视频重建任务
- **THEN** UI SHALL 显示依赖检查中的本地化状态
- **AND** 任务创建 SHALL 以可本地化的检查中错误拒绝
- **AND** 系统 MUST NOT 因等待外部工具扫描而阻塞页面交互

#### Scenario: 用户在设置页手动刷新依赖诊断
- **WHEN** 用户在设置页点击刷新视频重建诊断
- **THEN** 状态 API SHALL 支持显式刷新请求
- **AND** 系统 SHALL 更新进程级依赖缓存
- **AND** 后续视频重建弹窗和任务创建 SHALL 复用刷新后的状态

### Requirement: 系统 SHALL 提供适合本地 GPU 的安全质量默认值
系统 SHALL 提供受控质量档位，限制关键帧数量、分辨率或训练资源，避免默认配置轻易耗尽笔记本 GPU 显存。

#### Scenario: 用户选择质量档位
- **WHEN** 用户选择 `快速预览`、`高质量`、`极致` 或 `自定义`
- **THEN** 任务 SHALL 记录所选档位
- **AND** 管线 SHALL 应用与该档位关联的资源边界或用户提交的受控自定义参数

#### Scenario: 检测到 GPU 显存不足
- **WHEN** 重建任务因 GPU 显存不足失败
- **THEN** 任务 SHALL 失败并给出建议降低质量档位、减少关键帧或降低分辨率的用户可见提示
- **AND** 已存在的模型产物 MUST NOT 被删除

#### Scenario: 多个 GPU 重任务同时提交
- **WHEN** 用户提交多个图片生成或视频重建任务
- **THEN** 系统 SHALL 默认串行处理这些 GPU-heavy 任务
- **AND** UI SHALL 保留队列顺序和各任务状态

#### Scenario: 用户配置显存预算
- **WHEN** 本机 owner 在设置中配置显存预算
- **THEN** 后续视频重建任务 SHALL 使用该预算选择默认资源边界
- **AND** 非本机用户 SHALL 不能修改该全局默认配置

#### Scenario: 设置页解释质量档位差异
- **WHEN** 用户查看设置页的视频重建默认质量
- **THEN** UI SHALL 用简短文案说明各质量档的资源差异，例如帧数、训练迭代、输入分辨率或预期耗时
- **AND** UI SHALL 显示当前选择档位适合的用途，避免用户只看到抽象的“高质量/极致”

#### Scenario: 设置页解释引擎策略差异
- **WHEN** 用户查看设置页的视频重建默认引擎
- **THEN** UI SHALL 说明 `自动` 和 `稳定` 的差异
- **AND** UI SHALL 说明 `自动` 当前使用已验证稳定路线，并保留未来策略切换空间

#### Scenario: 质量档绑定特征匹配策略
- **WHEN** 用户选择不同质量档运行视频重建
- **THEN** 系统 SHALL 按质量档选择合适的相机特征匹配策略，在重建鲁棒性与耗时之间取得平衡
- **AND** 系统 SHALL 对高质量和极致档默认使用不依赖联网词表的完整匹配策略，优先保证相机注册完整
- **AND** 系统 SHALL 允许自定义参数选择可扩展匹配策略，用于优先覆盖长时间连续走拍视频，避免随帧数平方增长的完整匹配压力
- **AND** 系统 SHOULD 优先减少高质量和极致档的配准断链，即使因此需要更长的 COLMAP 匹配时间
- **AND** 系统 MUST NOT 保留没有 UI 或配置入口的隐藏匹配策略回退，避免实际行为和质量档说明不一致

#### Scenario: 配准相机过少时安全降级
- **WHEN** 几何阶段成功注册的相机数量过少，不足以安全运行默认相机采样策略
- **THEN** 系统 SHALL 自动改用不依赖最小相机数的采样策略，而不是让任务因采样断言失败而崩溃
- **AND** 系统 SHALL 记录该降级与实际注册相机数，便于解释重建质量

### Requirement: 视频重建 UI MUST 本地化
系统 MUST 为视频重建动作、弹窗、选项、依赖状态、任务阶段、权限提示、失败原因和设置项提供中英文文本。

#### Scenario: 语言切换时重建 UI 可见
- **WHEN** 用户在视频重建弹窗、任务队列或设置诊断可见时切换语言
- **THEN** 所有可见视频重建文本 SHALL 从当前语言资源渲染
- **AND** 英文和中文 locale 文件 SHALL 包含匹配 key

### Requirement: 视频重建弹窗 SHALL 延续现有玻璃态视觉
视频重建弹窗 SHALL 与项目现有 Settings 和主界面视觉一致，使用 Apple 玻璃态面板、可读文本层级、分段控件、状态卡片和响应式布局，并适配系统浅色/深色模式。

#### Scenario: 深色模式下打开视频重建弹窗
- **WHEN** 用户在深色系统模式或深色应用背景下打开视频重建弹窗
- **THEN** 弹窗 SHALL 使用半透明暗色玻璃背景、可见边框和足够文本对比度
- **AND** 选项、输入框、错误提示和主按钮 SHALL 与 Settings 页风格一致

#### Scenario: 浅色模式下打开视频重建弹窗
- **WHEN** 用户在浅色系统模式下打开视频重建弹窗
- **THEN** 弹窗 SHALL 使用浅色玻璃背景和足够文本对比度
- **AND** 依赖状态、禁用态和焦点态 SHALL 仍可读且可辨认

#### Scenario: 小屏设备打开视频重建弹窗
- **WHEN** 视口宽度不足以横向容纳三段式选项
- **THEN** 模式、质量和引擎选项 SHALL 自动改为可点击的单列布局
- **AND** 弹窗内容 MUST NOT 横向溢出或遮挡提交按钮

### Requirement: 系统 SHALL 保持现有图片生成和视频播放行为
新增视频重建 SHALL NOT 破坏现有图片生成、照片转 3D 或本地视频预览能力。

#### Scenario: 用户上传图片生成 3D
- **WHEN** 用户通过现有上传入口提交图片文件
- **THEN** 系统 SHALL 创建与当前行为一致的 SHARP 图片生成任务
- **AND** 完成的图片任务 SHALL 继续生成模型图库兼容的 `.ply` 和 `.spz` 产物

#### Scenario: 用户从相册照片转 3D
- **WHEN** 用户从本地相册选择照片并执行转 3D
- **THEN** 系统 SHALL 继续创建现有照片转换任务
- **AND** 视频 SHALL NOT 被错误提交到照片转换流程

#### Scenario: 用户预览本地视频
- **WHEN** 用户从媒体图库打开本地视频
- **THEN** 播放、下载、seek、音量、全屏、导航和关闭控制 SHALL 保持可用
- **AND** 新增重建操作 MUST NOT 阻塞或遮挡核心播放控制

### Requirement: 视频重建运行时垃圾 SHALL 被受控清理
系统 SHALL 在视频重建失败、取消或应用从上次中断恢复启动时，清理仅由当前 workspace 视频重建功能创建且不再被成功模型引用的临时文件、上传副本和残留进程。

#### Scenario: 任务失败或取消后清理受控临时产物
- **WHEN** 视频重建任务失败或进入 cancelled 状态
- **THEN** 系统 SHALL 按保留中间文件设置清理该任务的 `jobs/<task_id>` 临时目录
- **AND** 系统 SHALL 删除该任务预写但未完成的 sidecar、缩略图和未完成输出文件
- **AND** 如果源视频来自拖入上传缓存且没有成功模型引用，系统 SHALL 删除 `.video-reconstruction/uploads` 下对应源视频副本
- **AND** 系统 MUST NOT 删除本地相册中的原始视频文件

#### Scenario: 应用启动后清理上次中断残留
- **WHEN** 后端应用进程启动且 workspace 中存在上次中断留下的视频重建残留
- **THEN** 系统 SHALL best-effort 终止命令行或工作目录明确指向当前 workspace 视频重建目录的 Nerfstudio/COLMAP 残留进程
- **AND** 系统 SHALL 删除遗留的视频重建 job 目录
- **AND** 系统 SHALL 删除没有完成 `.ply` 模型引用的预写 sidecar 和孤儿上传缓存
- **AND** 系统 MUST NOT 删除已经被完成模型 sidecar 引用的上传源视频副本
- **AND** 清理失败 SHALL 记录日志且 MUST NOT 阻塞应用启动
