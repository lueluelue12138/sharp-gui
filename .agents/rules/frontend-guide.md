# 前端开发规范

## 组件规范

### 三件套结构

每个新组件 **必须** 遵循以下文件结构：

```
ComponentName/
├── ComponentName.tsx        # 组件实现
├── ComponentName.module.css # 样式（CSS Modules）
└── index.ts                 # 桶导出
```

`index.ts` 内容：
```typescript
export { ComponentName } from './ComponentName';
```

### 组件声明模式

**新代码统一使用命名导出的函数声明**（不使用 `React.FC`、不使用 `export default`）：

```typescript
// ✅ 正确 — 新组件必须使用此模式
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import styles from './MyButton.module.css';

interface MyButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  icon?: ReactNode;
}

export function MyButton({ variant = 'primary', icon, children, ...props }: MyButtonProps) {
  return (
    <button className={styles[variant]} {...props}>
      {icon && <span className={styles.icon}>{icon}</span>}
      {children}
    </button>
  );
}
```

```typescript
// ❌ 错误 — 新代码不要使用
export default function MyButton() { ... }     // 禁止 default export
export const MyButton: React.FC = () => { ... } // 新代码不用 React.FC
```

> **⚠️ 历史遗留（2026-04）**：以下情况在现有代码中存在，不要求一次性重构，但新代码必须遵循本规范。
>
> 1. `React.FC` 仍在部分组件中使用：`ViewerCanvas`、`Settings`、`ControlsBar`、`ParticleBackground`、`TaskQueue`、`Help`、`GyroIndicator`、`VirtualJoystick`、`SpeedTooltip`。
> 2. `App.tsx` 仍为 `export default`（应用入口历史遗留）。
> 3. 部分组件目录缺少 `index.ts`：`layout/ControlsBar/`、`layout/Help/`、`viewer/ViewerCanvas/`、`viewer/GyroIndicator/`、`viewer/VirtualJoystick/`。
> 4. `useXR.ts` 是当前统一的 VR + AR 实现；`useVR.ts` 为历史遗留文件，未被业务引用，新 XR 代码不要继续扩展它。

### Props 定义

- 使用 `interface XxxProps` 定义 Props
- 尽可能 `extends` 原生 HTML attributes（如 `ButtonHTMLAttributes<HTMLButtonElement>`）
- 使用解构赋值接收 Props，支持 `...rest` 透传

### CSS class 组合模式

使用数组 + `filter(Boolean).join(' ')` 模式：

```typescript
const classes = [
  styles.button,
  styles[variant],
  disabled && styles.disabled,
  className,
].filter(Boolean).join(' ');
```

### 组件分类

| 目录 | 用途 | 示例 |
|------|------|------|
| `components/common/` | 通用 UI 组件，不含业务逻辑 | Button, Modal, Loading, Icons, ImageViewer, ConfirmDialog, SelectMenu, TextInputDialog |
| `components/auth/` | 局域网门禁与启动安全提示 | AccessGate, AccessSetupPrompt |
| `components/gallery/` | 模型图库相关组件 | GalleryItem, GalleryList |
| `components/modelAssets/` | 模型资产库业务组件 | ModelAssetLibraryView, ModelAssetGrid, ModelAssetToolbar, ModelAssetDetailsPanel |
| `components/photoGallery/` | 本地媒体图库业务组件（历史目录名保留） | PhotoAlbumList, PhotoGalleryView, PhotoMasonryGrid, PhotoSelectionBar, PhotoToolbar |
| `components/layout/` | 页面布局与导航组件 | Sidebar, ControlsBar, Settings, Help |
| `components/viewer/` | 3D 查看器相关组件 | ViewerCanvas, QuickControls, ViewerRevealEffectsRail, GyroIndicator, VirtualJoystick, SpeedTooltip |

---

## 状态管理

### Zustand Store

项目使用 **单一扁平 Store**（`frontend/src/store/useAppStore.ts`）：

```typescript
import { create } from 'zustand';

interface AppState {
  // 状态字段
  isLoading: boolean;
  galleryItems: GalleryItem[];
  // ... 其他状态

  // Actions
  setLoading: (loading: boolean, text?: string) => void;
  setGalleryItems: (items: GalleryItem[]) => void;
  // ... 其他 actions
}

export const useAppStore = create<AppState>((set) => ({
  isLoading: false,
  galleryItems: [],

  setLoading: (loading, text) => set({ isLoading: loading, loadingText: text }),
  setGalleryItems: (items) => set({ galleryItems: items }),
}));
```

### Store 规则

- **单一 Store**：所有全局状态放在 `useAppStore` 中，不创建多个 Store
- **无中间件**：不使用 `persist` / `devtools` / `immer`
- **扁平结构**：状态字段直接放在顶层，不嵌套
- **Action 是箭头函数**：在 `create` 内部用 `set()` 修改状态
- **桶导出**：通过 `store/index.ts` re-export

当前 store 同时承载模型工作区与本地媒体图库工作区：

- `activeView` 在 `models` / `photos` 间切换；UI 文案可显示为“图库”，但状态值保持历史兼容。
- 旧模型图库兼容路径仍使用 `galleryItems`、`selectedModel` 等字段。
- 模型资产库使用 `modelAssets`、`modelAssetFilters`、`modelAssetSort`、`modelAssetDensity`、`modelAssetCursor`、`modelAssetHasMore`、`selectedModelAssetId`、`modelAssetSelectionMode`、`selectedModelAssetIds`、`modelAssetImporting` 等字段；不要把资产库列表再塞回旧 `galleryItems`。
- Viewer 当前模型使用 `currentModelSource` 区分 `gallery`、`model-asset-generated`、`model-asset-imported` 和 `temporary`；旧图库/任务刷新、删除和选择协调只能影响来源匹配的模型，不能因 id 偶然相同或旧列表响应而关闭资产库模型、临时 Blob 或其它来源。
- 本地媒体图库使用 `photoAlbums`、`currentPhotoAlbumId`、`photoItems`、`photoNextCursor`、`photoMediaType`、`photoSelectionMode`、`selectedPhotoIds`、`previewPhoto` 等独立字段，避免影响 3D 查看器状态。
- `PhotoItem.media_type` 支持 `image` / `video`，`photoMediaType` 支持 `all` / `image` / `video`；视频条目通过 `poster_url`、`playback_url`、`download_url` 和可选元数据驱动卡片与预览。
- 视频 3DGS 重建状态放在同一个 store 中的必要字段：重建弹窗打开状态、目标视频、默认配置、依赖诊断状态和提交中状态；不要为视频重建单独新建全局 store。
- 视频生成模型在 `GalleryItem` 中可带 `source_media_type` / `source_video_url` 等来源字段；列表操作应沿用现有 hover 后出现的图标按钮逻辑，不因视频模型而改成常驻按钮。
- 局域网门禁使用 `authStatus`、`isAuthenticated`、`isOwnerAccess`、`authSetupRequired`、`authPermissionError` 等字段；本机 owner 可进入设置，远程未解锁时必须展示门禁页或权限反馈。

### 使用方式

```typescript
// 组件中使用
const { isLoading, setLoading, galleryItems } = useAppStore();

// 或选择性订阅（性能优化）
const isLoading = useAppStore(state => state.isLoading);
```

---

## API 层

### 架构

```
api/
├── client.ts    # 底层 fetch 封装（apiGet, apiPost, apiPostFormData, apiDelete）
├── auth.ts      # 局域网门禁、访问码、会话与远程生成设置 API
├── gallery.ts   # 图库相关 API
├── modelAssets.ts # 模型资产库列表、详情、导入、封面、下载、删除 API
├── photoGallery.ts # 本地媒体相册、媒体列表、扫描、转换/下载 API
├── videoReconstruction.ts # 视频重建创建、上传创建与依赖诊断 API
├── tasks.ts     # 任务相关 API
├── settings.ts  # 设置相关 API
└── index.ts     # 桶导出（export * from 各模块）
```

### 底层客户端

`client.ts` 提供四个泛型函数：

```typescript
export async function apiGet<T>(url: string): Promise<T>;
export async function apiPost<T>(url: string, data?: unknown, options?: FetchOptions): Promise<T>;
export async function apiPostFormData<T>(url: string, formData: FormData, options?: FetchOptions): Promise<T>;
export async function apiPostFormDataWithProgress<T>(url: string, formData: FormData, options?: ProgressFetchOptions): Promise<T>;
export async function apiDelete<T>(url: string): Promise<T>;
```

> `apiPostFormDataWithProgress` 基于 `XMLHttpRequest` 暴露上传进度回调，供模型资产导入这类大文件上传显示进度；仅对后端已有请求级大小/数量约束的受控大文件请求可显式使用 `timeout: 0`，普通请求继续使用默认超时和基于 `fetch` 的函数。

特性：
- **原生 fetch**，不使用 axios
- **30 秒超时**（AbortController）
- **自定义错误类** `ApiError`（携带 `status` 和 `data`）
- **泛型返回值** `Promise<T>`
- **同源凭证**：默认携带 same-origin Cookie，门禁会话依赖 HttpOnly Cookie，不要改成无凭证请求

### 新增 API 规则

1. 在对应的功能模块文件中添加函数（或创建新模块文件）
2. 使用泛型指定返回类型：`apiGet<MyResponse>('/api/my-endpoint')`
3. 在 `api/index.ts` 中确保 `export *` 导出
4. 对应的类型定义放在 `types/` 目录
5. 新增私有 API 时必须确认后端 `get_required_access_level()` 已分类，并在前端区分 401（未解锁）与 403（权限不足）

视频重建 API 约定：

- 从相册视频创建任务调用 `POST /api/video-reconstructions`，只传 `video_id`、`mode`、`quality`、`engine`、`output_name` 等安全字段。
- 从拖入视频创建任务时，先打开视频重建弹窗；用户提交后再调用 `POST /api/video-reconstructions/upload`，使用 `FormData` 上传单个视频文件。
- 依赖状态调用 `GET /api/video-reconstructions/status`；Settings 手动刷新才传 `?refresh=1`，普通首页、弹窗打开和提交任务前不得重复触发刷新扫描。
- source video 预览使用图库条目的 `source_video_url`，fallback 为 `/api/gallery/<id>/source-video`；前端不得推断或拼接服务器绝对路径。

---

## 自定义 Hooks

### 命名与导出

```typescript
// ✅ 标准模式
export const useMyHook = (param: ParamType) => {
  // hook 实现
  return { value, action };
};
```

### 常见模式

| 模式 | 说明 | 示例 |
|------|------|------|
| Viewer 操作 | 接收 `viewerRef` 参数操作 3D viewer | `useKeyboard(viewerRef)` |
| 动画循环 | 使用 `requestAnimationFrame` + `useRef` | `useGyroscope`, `useJoystick` |
| 图库性能 | 组合虚拟滚动、缩略图/poster 预加载与稳定高度；媒体图库列表只加载缩略图或 poster，预览才加载原图/视频流 | `useGalleryVirtualizer`, `useGalleryThumbnail` |
| 模型资产 | 组合封面队列、格式偏好和资产源选择；列表只加载当前批次和缩略图/封面，详情再请求完整字段 | `useModelAssetCoverQueue`, `resolveModelAssetSource` |
| 任务轮询 | 根据队列状态调整刷新频率 | `useTaskQueue` |
| 状态引用 | 使用 `useRef` 管理不触发重渲染的状态 | 各 3D 相关 hook |
| 组合模式 | 主 hook 内部调用子 hook | `useViewer` 组合 `useKeyboard` + `useGyroscope` + `useJoystick` + `useXR` |

### 位置

所有自定义 Hooks 放在 `frontend/src/hooks/` 目录，一个文件一个 Hook。

---

## TypeScript 类型系统

### interface vs type

| 场景 | 用哪个 | 示例 |
|------|--------|------|
| 对象结构、API 响应、组件 Props、Store 状态 | `interface` | `interface GalleryItem { ... }` |
| 联合类型、字面量类型 | `type` | `type TaskStatus = 'pending' \| 'running'` |
| 类型别名 | `type` | `type IconProps = SVGProps<SVGSVGElement>` |

### 类型位置

| 类型 | 位置 |
|------|------|
| API 响应 / 业务实体 | `types/` 目录下对应文件 |
| 组件 Props | 组件文件内（与组件同文件） |
| Store 状态 | `store/useAppStore.ts` 内 |
| 工具函数参数/返回值 | 工具函数文件内 |

### 类型导出

```typescript
// types/index.ts — 桶导出
export type { GalleryItem, GalleryListResponse } from './gallery';
export type { Task, TaskStatus, TasksResponse } from './task';
export type { CameraConfig } from './viewer';
```

### TypeScript 配置要点

- `strict: true` — 严格模式
- `verbatimModuleSyntax: true` — 必须使用 `import type` 导入纯类型
- `noUnusedLocals: true` — 不允许未使用的局部变量
- `noUnusedParameters: true` — 不允许未使用的参数
- 路径别名：`@/*` → `src/*`

---

## 性能优化

> 不要过度优化，以下是需要关注的场景：

### 何时使用 `React.memo`

- 组件接收 **大列表中的单项** 数据（如 `GalleryItem`）
- 父组件频繁重渲染但当前组件 props 不变
- **不要**默认给所有组件加 `memo`，先用 React DevTools 确认存在性能问题

### 何时使用 `useMemo` / `useCallback`

- 传递回调给 `memo` 化的子组件时
- 计算开销大的派生数据（如过滤/排序长列表）
- **不要**对简单计算使用 `useMemo`（anti-pattern）

### 3D 渲染注意事项

- 动画循环已在 `useViewer` 中通过 `requestAnimationFrame` 管理，不要创建额外的渲染循环
- Three.js 对象（Geometry、Material、Texture）手动创建时需在 cleanup 中 `.dispose()`
- 避免在 React render 中创建 Three.js 对象（应该在 `useEffect` 或 `useRef` 中）

### 懒加载

对大型页面级组件可使用 `React.lazy` + `Suspense`（当前项目为单页应用，暂无需要）。

### 本地媒体图库性能

- 应用 boot 不应 await 本地媒体图库相册内容；默认只完成认证、设置、模型等必要数据，图库摘要在进入 `photos` 视图后按需加载。
- 相册入口页只请求相册摘要、封面和扫描状态，不应预拉每个相册的媒体列表。
- 相册媒体列表必须分页加载，不要一次性把大目录全部塞进 DOM。
- 瀑布流图片使用 `thumb_url`、视频使用 `poster_url` 或 fallback 卡片，配合 `loading="lazy"`、`decoding="async"` 和稳定 `aspect-ratio`。
- 列表与离屏卡片不能加载完整视频文件；只有进入视频预览时才使用 `playback_url` 请求视频流。
- 图片预览层使用 `full_url` / `preview_url` 原图地址，不能复用缩略图放大；视频预览层使用 `playback_url`，下载使用 `download_url` 或 API helper。
- 网格密度调节和触控捏合只改变展示列数，不重新扫描相册。
- 切换类型筛选、排序、网格密度或多选状态不得触发重新扫描；只应重置/请求当前相册分页数据。
- 多选状态只存储 media id 集合，避免复制大对象；视频可下载但不可加入照片转 3D。
- 视频可以从本地媒体图库、视频预览层、模型视图空态/主画布、模型列表区域和「生成新模型」入口触发重建；多个视频或视频+图片混合拖入时必须给出明确提示。
- 视频预览层触发重建时，应先关闭或让出视频预览 overlay，再打开视频重建弹窗；弹窗不得被视频预览层遮挡。
- 从模型视图、模型列表区域或「生成新模型」入口拖入单个视频时，应打开同一视频重建弹窗，不得绕过配置直接提交重建任务。
- 视频重建弹窗必须延续 Settings 同一套玻璃态视觉、浅色/深色适配和分段控件层级；不要使用普通白底表单、浏览器原生 `alert` 或割裂的临时样式。
- 视频重建模型列表缩略图优先使用源视频封面；没有可用缩略图时才展示克制 fallback。原视频预览入口应和单图模型下载/删除等操作一样遵循 hover/触控可达逻辑。

### 模型资产库性能与交互

- 模型资产库列表必须使用后端游标和固定批次增量加载，不显示分页器或“每页数量”控件；滚动接近底部时请求下一批，来源/格式/标签/排序变化重置查询并请求首批。
- 资产网格密度只改变 CSS 展示列数，必须保留已加载列表、游标和滚动上下文，不调用列表 API、不重新扫描模型目录，也不影响后端批次大小常量。
- 首屏、筛选、排序和追加请求必须绑定单调递增的 request generation、完整 query signature 与预期游标；只有仍匹配当前查询的响应可以更新列表、筛选、游标、loading 或 error，切换查询时应 Abort 或逻辑废弃全部旧请求，避免慢响应把 Store 反向改回旧筛选。
- 卡片只加载缩略图、源媒体 poster 或缓存封面；完整详情和可解析元数据在打开详情面板时按需获取。
- 桌面端点击卡片按钮之外区域应直接打开模型预览；hover/focus 操作按钮分别处理查看详情、下载、删除等动作，并阻止事件冒泡。
- 触控端不能依赖 hover 才能触达操作。移动端点击卡片可打开详情卡片，再通过详情卡片执行当前来源和权限允许的打开、下载、导出、删除；缩略图本身可打开关联原图/视频。
- 顶部工具栏复用照片图库的玻璃态浮动逻辑和移动端收缩/展开模式；不得用实心黑背景切断卡片滚动内容。

#### 模型资产导入与临时预览

- 主模型页拖入一个受支持模型时只创建本地 Object URL 并标记为 `temporary`，让用户明确选择“加入资产库”；拖入多个受支持模型时批量导入。资产库视图内拖入一个或多个文件都直接走批量导入，并逐项显示不支持格式或校验失败原因。
- 临时 Object URL 在替换、关闭、组件卸载和持久化导入成功时都必须 `URL.revokeObjectURL()`；导入是否成功与新资产是否立刻可打开分开判断，不能因响应暂缺 URL 而保留可重复导入的临时态。
- 批量响应在 2xx 部分成功与非 2xx 全失败时都必须保留 `failed[]`。前端按文件名关联失败项并按稳定 `code` 本地化，不能用一个顶层 `HTTP 400`、后端英文或 `Unknown error` 覆盖所有文件原因。
- 导入成功后的列表合并使用当前查询条件，不清空筛选、选择和滚动上下文；任务完成增量同步资产摘要（以及任何保留的旧图库兼容刷新）时，同样不得改变正在查看的非 `gallery` 模型。

#### 模型资产能力与操作边界

- 模型资产能力拆分为读取、受控写入和 owner 删除：`canWriteModelAssets = isOwnerAccess || (authStatus.access_control_enabled && isAuthenticated && authStatus.allow_remote_generation)` 用于导入、资料编辑和封面上传/刷新；`canDeleteModelAssets = isOwnerAccess` 仅用于删除。无权操作应隐藏或禁用并提供本地化原因，不能只依赖后端 403 兜底。
- `gallery` / `model-asset-generated` 可复用旧生成结果的导出与分享；`model-asset-imported` / `temporary` 在没有专用受控实现前不得调用 `/api/export/<id>` 或旧分享接口，入口使用禁用态或省略态且解释清楚。
- 打开资产必须传最终解析出的 URL、格式、真实文件大小和来源类型；不可用资产没有打开/下载入口，不能仅凭索引里的格式展示一个必然 404 的操作。
- 模型资产流程的权限、导入、删除、封面和查询错误使用应用内通知/对话框，不得调用浏览器原生 `alert` / `confirm` / `prompt`。

#### 模型资产封面与复合卡片

- 后端 `thumb_url` 是权威封面；缺封面的导入资产只对已加载且可见或刚导入的条目排队，失败时显示格式感知占位并采用有限退避/显式重试，不能在每次刷新后无限重试全部历史资产。
- 封面任务总并发必须有上限。网络/文件处理可以并发，但同一个 WebGL renderer/canvas 的 `render → settle frames → toBlob` 区间必须串行；若需要同时渲染两个模型，应使用互不共享 canvas 的 renderer worker，完成回调还要核对 asset id 和当前挂载代次。
- 卸载时停止继续入队，过期完成回调不得写组件局部状态；若任务已成功持久化封面，可按 asset id 更新全局资产摘要以避免重新入队。释放 Spark/Three 模型、纹理、render target、Object URL 等资源；共享 renderer 由明确的生命周期持有者统一复用和销毁。
- 可点击卡片包含快捷按钮时，不得用一个 `role="button"` 容器包裹其它 `<button>` 并让 Enter/Space 冒泡触发父动作。主卡片动作与详情、下载、删除等快捷动作使用语义独立元素；若保留父键盘处理，仅在 `event.target === event.currentTarget` 时激活。

### 视频预览交互

- 视频播放内核使用原生 `<video>` + 自定义 CSS Modules 控制层，不引入重型播放器 UI 框架；解码、缓冲、Range seek 和硬件加速交给浏览器。
- 移动端视频元素应带 `playsInline`、`webkit-playsinline`、`x5-video-player-type="h5-page"`、`controlsList="nodownload noremoteplayback"`，并禁用画中画/远程播放；这些属性只能尽量降低安卓浏览器接管概率，不能承诺覆盖所有私有浏览器。
- 播放失败态必须保留下载和关闭操作，并使用项目一致的玻璃态卡片/按钮；不要临时拼一个高饱和胶囊或浏览器原生提示。
- 视频预览中点击/触控视频画面应切换自定义控制栏显隐，不直接切换播放/暂停；播放状态只由中心播放按钮、控制栏播放按钮或明确键盘快捷键改变。
- 视频预览应支持常见键盘控制：空格播放/暂停，左右方向键 seek，上下方向键调节音量，`F` 进入/退出全屏；打开预览后应主动聚焦预览层，普通按钮焦点不应阻断播放器级快捷键，输入框、下拉框、文本编辑区和 range 滑块应保留自身键盘行为。
- 移动端可支持长按视频画面横向拖动进行精细 scrub；桌面端不要启用画面拖动 seek，保留进度条和键盘操作。
- 移动端横屏视频进入全屏时可以尝试 `screen.orientation.lock('landscape')`，失败必须静默降级并释放方向锁。
- 控制栏需要在 PC、平板竖屏、手机竖屏等中间宽度保持完整：按钮不可截断，文件名不可遮挡控制栏，折叠状态点击非按钮区域只展开控制栏，不强制滚动页面。

---

## 错误处理

### API 调用

所有 API 调用必须在组件/Hook 中 try-catch：

```typescript
import { useAppStore } from '@/store';

const handleAction = async () => {
  try {
    const result = await someApiCall();
    // 处理成功
  } catch (error) {
    // 使用 store 中的通知/loading 机制反馈给用户
    console.error('操作失败:', error);
  }
};
```

局域网门禁相关错误处理约定：

- 401 表示当前远程设备未解锁，入口层应切换到 `AccessGate`，不要继续渲染私有图库数据。
- 403 表示已登录但权限不足，通常是远程设备触发 owner-only 操作，应显示本地化权限反馈。
- 设置页中的门禁开关、访问码、会话天数、远程生成和撤销会话必须调用 `auth.ts`，不要绕过 Store 状态直接假定保存成功。

### 错误边界（Error Boundary）

如果未来需要添加，推荐在 3D Viewer 区域包裹错误边界，防止渲染崩溃导致整个页面白屏。当前项目未添加，作为改进方向记录。

---

## 构建与分包

Vite 配置了 `manualChunks` 代码分割：

| Chunk | 包含 | 大小参考 |
|-------|------|----------|
| `three` | three.js 核心 | ~493KB |
| `spark` | @sparkjsdev/spark | ~487KB |
| `react-vendor` | react, react-dom | ~4KB |
| `utils` | i18next, zustand | ~20KB |

新增大型三方依赖时，应在 `vite.config.ts` 的 `manualChunks` 中配置独立 chunk。

---

## 3D 渲染引擎

### Spark（替代 Gaussian Splats 3D）

项目已从 `@mkkellogg/gaussian-splats-3d`（已停止维护）迁移至 `@sparkjsdev/spark` 2.0 稳定版：

| 特性 | 说明 |
|------|------|
| **SplatMesh** | 继承 `THREE.Object3D`，可直接 `scene.add(splatMesh)` |
| **SparkRenderer** | 继承 `THREE.Mesh`，作为渲染管线的一部分加入场景 |
| **RAD + paged** | 支持 `.rad` 头文件 + `.radc` 分块流式加载 |
| **WASM Raycaster** | 内置 WASM 加速射线检测，用于点击聚焦（`splatMesh.raycast()`） |
| **GsplatModifier** | 用于 Reveal Effects（Magic / Spread / Unroll / Twister / Rain）等渲染特效 |

当前 React 查看器支持的模型格式：`.ply`、`.splat`、`.spz`、`.rad`。后端默认生成 `.ply`，并自动转换 `.spz` 供默认查看/下载。视频重建模型也进入同一模型图库和 Spark Viewer，不应引入第二套查看器。

### 关键代码模式

```typescript
// 初始化 Spark 渲染器
const sparkRenderer = new SparkRenderer({ renderer });
scene.add(sparkRenderer); // 必须加入场景

// 加载模型（LoD + nonLoD 对比能力）
const splatMesh = new SplatMesh({
  url,
  fileType: SplatFileType.SPZ,
  lod: true,
  nonLod: true,
});
await splatMesh.initialized;
scene.add(splatMesh);

// 即时切换 LoD 对比源
splatMesh.enableLod = true;
splatMesh.lodScale = 1.0;

// 点击聚焦（WASM Raycaster）
const raycaster = new THREE.Raycaster();
const intersects = raycaster.intersectObject(splatMesh);
```

### 注意事项

- **模型朝向**：加载后需设置 `splatMesh.rotation.x = Math.PI` 纠正模型上下颠倒
- **视频模型坐标适配**：Nerfstudio/Splatfacto 视频重建模型可能是 Y-front 形态；适配应优先在模型侧隐藏 orientation 中完成，使 camera/OrbitControls 保持默认 `Y-up / -Z forward / polar≈90°` 的干净状态。不要通过把相机初始极角推到 0°/10° 或切换异常 up 向量来“看起来调正”，这会导致左右拖拽变成 roll。
- **缩放**：通过 `splatMesh.scale.setScalar(modelScale)` 控制（默认 2.0）
- **清理**：切换模型或组件销毁时调用 `splatMesh.dispose()`，并销毁 `sparkRenderer`
- **listenToKeyEvents**：不可调用 `OrbitControls.listenToKeyEvents()`（Spark 注册的全局 listener 与之冲突）
- **Reveal Effects**：效果选择与默认值走 Zustand + localStorage，用户可见文案必须同步 `en.json` / `zh.json`
- **Quick Controls**：模型姿态、交互方向和质量覆盖按模型持久化，新字段需同步更新 `types/viewerQuickControls.ts`
- **调试读数**：Quick Controls 中的相机/OrbitControls/模型姿态/包围盒调试数据可以保留，用于排查视频模型坐标系；新增字段仍需中英文 i18n 和复制输出一致性。

---

## WebXR（VR / AR）

### 架构

XR 功能由 `useXR` hook 统一管理（替代了原来的 `useVR`），支持双模式：

| 模式 | WebXR Session | 特性 |
|------|--------------|------|
| **VR** | `immersive-vr` | Camera Rig 漫游、手柄摇杆控制、A/X 键重置 |
| **AR** | `immersive-ar` | 透明背景 Passthrough、触摸旋转/升降、双指缩放 |

### Camera Rig 模式

使用 `THREE.Group` 作为相机父级（Camera Rig），移动 rig 而非直接操作相机：

```typescript
const rig = new THREE.Group();
rig.add(camera);
scene.add(rig);

// 移动：修改 rig.position
// 转向：修改 rig.rotation.y
```

### 关键实现细节

- **高度校准**：`local-floor` 参考空间将头部置于 ~1.6m，需 `rig.position.y = -xrCam.position.y` 使模型在眼前
- **Home 位置**：`rigHomeRef` 保存校准后的位置，A/X 重置时恢复到校准位置而非 (0,0,0)
- **Session 结束恢复**：需完整恢复 camera (position, up, rotation, fov, near, far)、renderer (viewport, pixelRatio)、controls (target, update)
- **AR 透明背景**：进入 AR 时 `scene.background = null` + `renderer.setClearColor(0,0,0,0)`
- **AR 缩放恢复**：退出 AR 时需恢复 `splatMesh.scale` 到原始值
