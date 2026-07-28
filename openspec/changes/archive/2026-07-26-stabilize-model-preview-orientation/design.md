## Context

当前 React + Spark Viewer 同时承担三件不同的事：

1. 根据模型来源修正模型坐标方向；
2. 根据世界包围盒计算相机目标点、居中条件和适配距离；
3. 叠加并持久化用户在 Quick Controls 中设置的旋转、位移和缩放。

这三类状态目前没有清晰边界。模型资产库迁移后，后端已经提供的 `source_type` / `source_media_type` 没有随“当前模型”完整传入 Viewer，Viewer 仍尝试从不再是主数据源的 `galleryItems` 反查来源。来源反查失败时，`useViewer.ts` 会用包围盒比例 `z / max(x, y) < 0.65` 猜测模型是否需要 Y-front 适配，并在相机重置期间修改模型方向。

问题样本 `img-7f18fe7dd29e4890987eab0b49313ca8.spz` 的包围盒约为 `9.29 × 6.70 × 4.86`，恰好命中该阈值；隐藏 `RotX(+90°)` 与现有用户基线旋转合成后，初始画面变成顶视图。对比图片样本的深度比例没有命中，所以表现正常。由此可见，包围盒形状只能描述空间占用，不能可靠表达“正面”或生成管线的坐标语义。

外部格式也不能代替来源元数据：ML-SHARP 明确输出 OpenCV 坐标约定；PLY 本身不是场景描述格式且不携带通用变换矩阵；SPZ 新规范虽定义默认坐标系和坐标系扩展，但本项目现有 PLY→SPZ 路径保持输入坐标，不能仅凭 `.spz` 后缀推断方向。Three.js `OrbitControls` 则适合维持稳定的 `+Y` up 相机轨道，因此来源差异应在模型侧规范化，而不是把相机推到极角奇点。

本变更涉及后端任务元数据、模型资产 API、Zustand 当前模型状态、多个打开入口、Viewer、Quick Controls、调试读数和中英文文案，适合用一个小型的预览方向契约统一处理。

参考：

- [Apple ML-SHARP](https://github.com/apple/ml-sharp)
- [Niantic SPZ](https://github.com/nianticlabs/spz)
- [PLY format description](https://paulbourke.net/dataformats/ply/index.html)
- [Three.js OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)
- [Three.js Camera](https://threejs.org/docs/pages/Camera.html)

## Goals / Non-Goals

**Goals:**

- 图片、视频、导入、临时和可安全识别的旧模型都得到确定、可解释且互不污染的初始方向。
- 以一个很小的显式 `viewer_orientation` 契约取代包围盒方向猜测，并完整贯穿模型资产的 list、recent、detail、open、reload 与格式切换链路。
- 保留现有视频模型侧 Y-front 修正，同时确保正常图片模型和异常扁平图片模型都维持图片基线方向。
- 让方向解析、用户变换和相机取景成为三个独立阶段；重复重置不会累积旋转。
- 同一资产的 PLY/SPZ 等伴随格式共享稳定资产 ID、来源方向和用户覆盖。
- 复用现有 Quick Controls 与 localStorage v1 覆盖结构，加入足够的自动化测试和双语诊断，不引入新的前端测试框架或运行时依赖。

**Non-Goals:**

- 不用 AABB、PCA、图像语义或 AI 自动寻找任意模型的“正面”。
- 不实现完整的 16 种坐标系注册表、矩阵编辑器或自动解析 SPZ v4 扩展。
- 不根据 PLY/SPZ/SPLAT/RAD 文件扩展名直接推断坐标语义。
- 不批量改写历史 sidecar 或模型文件，不修改 `ml-sharp/`、legacy 前端和 `static/lib/`。
- 不改变当前正常图片使用的包围盒居中与适配距离策略，也不重构整个 `useViewer`。
- 本次不实现服务器端、多设备同步的用户方向偏好；外部导入模型继续使用现有本地逐模型覆盖。

## Decisions

### 1. 使用显式、最小化的预览方向契约

前后端共享一个可选的归一化提示：

```text
ViewerOrientationHint = "default" | "y-front" | "unknown"
EffectiveOrientation = "default" | "y-front"
```

- `default`：使用当前 Viewer 图片/通用模型基线，不添加来源校正。
- `y-front`：在用户变换之前应用现有模型侧 `RotX(+90°)` 校正。
- `unknown`、缺失或非法值：有效方向保守回退为 `default`，但诊断原因保留为 unknown/fallback，用户仍可使用现有方向预设手动纠正。

解析优先级为：

1. 模型资产或 sidecar 中合法的显式 `viewer_orientation`；
2. 可信来源映射：`source_media_type=image` → `default`，`source_media_type=video` 或受控视频任务来源 → `y-front`；
3. 现有安全 legacy video backfill；
4. `unknown` → 有效 `default`。

新图片任务写入 `viewer_orientation: default`，新视频任务写入 `viewer_orientation: y-front`。旧 sidecar 无需迁移，可在资产投影时由可信来源派生。`coordinate_system` 如未来出现，只作为事实/诊断字段；它与展示适配指令 `viewer_orientation` 不混用。

**Why:** 显式提示能够表达生成管线已知的坐标语义，又把未知外部文件保持在安全默认值；三值契约足够覆盖当前产品，不需要引入通用矩阵协议。

**Alternatives considered:**

- 继续调整或删除 `0.65` 阈值：改动更小，但调阈值仍会误判，直接删除又会让缺少上下文的旧视频失去适配。
- 只把 `source_media_type` 传给 Viewer：可以修复本次问题，但让 Viewer 永久耦合后端来源名称，难以表达未来明确导入的坐标语义。
- 建立完整 canonical coordinate registry：长期更通用，但当前转换器、旧格式和 UI 都没有完整坐标描述，实施与迁移成本明显超过本次需求。

### 2. 当前模型改为对象描述符，方向上下文不再旁路反查

把易漏字段的 `setCurrentModel(id, url, format, size, source)` 收束为对象式 `CurrentModelDescriptor`，至少包含：

```text
id, url, format, size, source,
sourceMediaType, viewerOrientation
```

资产列表、最近模型、详情页、格式切换、生成完成、导入完成、临时 Blob 和设置触发的 reload 都使用同一描述符。稳定资产使用资产 ID；临时预览使用本次加载作用域内的临时 ID。Viewer 只读取当前描述符，不再从 `galleryItems` 反查方向。

**Why:** 对象参数使新增上下文在类型层面可见，避免第六、第七个位置参数继续在某个入口被遗漏；它也明确了格式 URL 与资产级预览语义的区别。

**Alternatives considered:**

- 给现有 setter 增加一个位置参数：补丁较小，但已有多个入口已证明这种接口很容易漏传。
- Viewer 内自行请求模型详情：增加竞态、重复请求和缓存一致性问题，也让渲染层依赖 API。

### 3. 固定为“解析方向 → 合成变换 → 计算包围盒 → 相机取景”

每次模型加载只解析一次方向，并把解析结果保存在该次 `ViewerContext` 中：

```text
preview descriptor
  → resolve source orientation
  → sourceQuaternion × userQuaternion
  → update world matrix and world-space bounds
  → frame camera from bounds
```

保留当前 `userQuaternion.premultiply(sourceQuaternion)` 的合成顺序，避免视频交互手感变化。删除 `shouldUseYFrontResetOnBounds` 以及相机 reset 内修改 `orientationMode` 的分支。AABB 继续用于中心、target 和 fit distance；正常图片保留原有居中条件，已解析为 Y-front 的模型则保留现有 bounds-centered 取景策略。这里的 Y-front 只选择相机取景策略，不能由 bounds 推断，也不能在 reset 中反向修改模型方向。相机维持 `+Y` up、默认朝本地 `-Z`，已验证视频的初始 orbit polar 保持在约 `90°`，不再以 `180°` 极角补偿模型方向。

**Why:** 模型方向属于模型语义，包围盒属于取景输入。先得到最终模型世界矩阵再计算 bounds，能让图片和视频共享同一套稳定相机原语，同时保留已验证视频原有的居中适配。

**Alternatives considered:**

- 通过相机 `up`、forward 或 polar 补偿：容易进入 OrbitControls 极点并让交互轴与用户直觉不一致。
- 在生成或转换时重写模型坐标：会改变用户文件和格式转换语义，回滚与兼容风险更高。

### 4. 来源校正与用户 Quick Controls 覆盖独立持久化

来源方向是运行时基线，不写入 `modelViewerOverrides`。现有 localStorage v1 结构继续只保存用户可编辑的 transform、interaction 和 quality，并按稳定资产 ID 索引：

```text
effective model transform = source correction × saved user transform
```

语义保持为：

- 重置相机：只重算 target、camera position 和 distance；
- 重置方向/选择 Default 预设：清除用户旋转到当前 Viewer 用户基线，来源校正仍保留；
- 重置全部 Quick Controls：删除该稳定资产 ID 的用户覆盖，回到来源派生的预览基线。

同一资产在 PLY/SPZ 间切换只替换 URL/decoder，不建立第二份方向或用户覆盖。

**Why:** 自动校正不应污染用户数据；沿用 v1 覆盖结构可避免迁移和已有偏好丢失。

**Alternatives considered:**

- 把隐藏校正写入保存的 rotation：会在重开、格式切换和再次解析来源时重复累积。
- 本次新增独立的 Auto/Default/Y-front 用户基线字段：有一定价值，但现有方向预设已能处理低优先级外部模型；先保留为后续小扩展，避免扩大状态迁移范围。

### 5. 后端负责投影可信事实，前端负责纯函数解析

后端在图片/视频任务 sidecar 写入显式提示，并由模型资产服务把提示与 `source_media_type` 一起投影到摘要和详情响应。旧模型只复用现有保守 backfill：仅在证据唯一且可信时识别视频，歧义或无证据时返回 unknown；不得在每次 warm pagination 中全盘扫描，也不批量重写旧文件。

前端把优先级和非法值处理抽为无 Three.js 依赖的纯函数（例如 `viewerOrientation.ts`），Viewer 只消费解析后的模式与 reason。API 字段保持可选，因此后端先上线或前端先上线都能兼容。

**Why:** 后端最了解模型来源，前端最了解展示基线；纯函数边界便于使用项目现有 `node:test` 做快速回归。

**Alternatives considered:**

- 所有映射都放在后端并只返回最终布尔值：诊断信息不足，也不利于临时 Blob 和离线状态。
- 所有推断都放在前端：会复制 legacy 识别逻辑，并再次依赖不完整列表状态。

### 6. 分开报告方向决策与相机取景

调试读数不再使用含混的 `bounds-y-front`。它分别显示：

- orientation mode：`default` / `y-front`；
- orientation reason：explicit hint / image metadata / video metadata / legacy backfill / unknown fallback；
- framing mode：bounds centered / bounds default / bounds unavailable / fallback。

所有用户可见标签同步更新 `en.json` 与 `zh.json`。加载上下文绑定 generation token 或等价的当前加载检查；旧加载完成或取消时不得写入新模型的方向、bounds 或 debug state。

**Why:** 方向和取景分栏能直接解释此次故障，也使未来报告更容易定位是元数据、变换还是相机问题。

**Alternatives considered:**

- 继续扩展 reset mode 枚举：会把两个独立维度继续组合成越来越多的状态。

### 7. 使用轻量分层测试，不引入新框架

- 前端用现有 `node:test` 模式测试纯解析函数、优先级、unknown 回退和模型切换数据；不为此次变更引入 Vitest。
- 后端 pytest 覆盖图片/视频 sidecar、资产 list/detail 投影、安全 legacy backfill 和伴随格式一致性。
- 人工回归固定使用用户给出的异常图片、正常图片、一个视频重建 PLY/SPZ 配对样本，以及 imported/temporary 模型。

**Why:** 绝大多数风险集中在可纯测的契约和状态传播上，轻量测试足以提供高价值保护；Three.js 最终视觉仍由小型人工矩阵验证。

**Alternatives considered:**

- 本次搭建完整 DOM/WebGL 测试环境：成本高、易产生渲染环境噪声，不符合此次修复规模。

## Risks / Trade-offs

- [缺少可信元数据的旧视频不再被 AABB 自动扶正] -> 复用现有唯一视频证据 backfill，并保留 Quick Controls 手动预设；不以误伤图片换取猜中未知视频。
- [方向字段在某个打开或 reload 入口再次丢失] -> 使用对象式描述符和穷举入口测试，禁止 Viewer 旁路反查。
- [快速切换或取消加载导致上一模型的 Y-front 泄漏] -> 将解析结果绑定 Viewer load generation/context，只允许当前加载提交方向、bounds 与诊断状态。
- [变换合成次序调整导致已有视频交互回归] -> 保持当前 premultiply 次序，并对有/无用户覆盖、重复 reset、PLY/SPZ 切换做 quaternion 回归。
- [模型资产缓存返回旧摘要而缺少新字段] -> API 字段可选并前端安全回退；刷新/重建资产索引时补齐投影，不在 warm page 做昂贵扫描。
- [显式 hint 与来源字段冲突] -> 合法显式 hint 优先，同时在诊断中报告决策来源，便于发现生产端错误。
- [本次不解析完整坐标系会限制部分第三方模型自动适配] -> unknown 保守展示并复用手动预设；把 `coordinate_system` 保留为独立演进点，待真实格式需求出现再扩展。

## Migration Plan

1. 后端先增加可选 `viewer_orientation` 写入、归一化与资产投影；旧前端会忽略该字段。
2. 前端增加类型、纯 resolver 和对象式 `CurrentModelDescriptor`，更新全部打开与 reload 入口；缺失字段仍安全回退。
3. Viewer 在加载阶段消费解析结果，删除 AABB Y-front 推断，并把 reset 限定为相机取景。
4. 保持现有 localStorage v1 覆盖数据不迁移，验证来源校正与用户变换的现有合成次序。
5. 更新双语调试读数和自动化测试，然后执行固定人工回归矩阵。

验证点：

- 两个指定图片样本均以图片基线打开，异常样本不再进入 Y-front；
- 视频模型 PLY/SPZ 均保持现有正确方向，camera up 为 `+Y` 且初始 polar 约为 `90°`；
- imported/temporary 未知模型不因扁平 bounds 自动旋转；
- image → video → image 快速切换、取消加载、格式切换和重复 reset 均不泄漏或累积方向；
- 已保存 Quick Controls 覆盖能在重开和格式切换后保持。

回退策略：

- 后端新增字段为可选且不改写历史文件，可单独保留；
- 若 Viewer 回归，可回退前端 descriptor 消费与方向 resolver，旧前端会忽略后端字段；
- 不删除或迁移 localStorage v1 数据，因此回退不会丢失用户设置；
- AABB Y-front 分支只在上述回归矩阵通过后移除，版本回退仍可恢复旧行为。

## Open Questions

本次没有阻塞实现的问题。以下扩展明确延后：

- 是否给高级用户增加逐模型 `Auto / Default / Y-front` 基线选择，并作为独立字段持久化；
- 是否在第三方 SPZ v4 或其他模型来源实际出现后，解析 `coordinate_system` 并建立格式适配器；
- 是否把导入模型的手动方向偏好从本地覆盖升级为服务端资产元数据，以支持多设备同步。
