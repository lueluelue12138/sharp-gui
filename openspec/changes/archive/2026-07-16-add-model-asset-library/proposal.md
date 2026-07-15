## Why

当前模型入口仍以侧栏列表为主，模型数量增多后浏览、筛选、选择和回看效率明显低于现有本地媒体图库。用户希望模型页升级为接近示例图的模型资产库体验，并支持本机与局域网设备导入外部 3D Gaussian Splatting 模型，使项目生成结果和外部模型都能进入统一管理、预览、下载和查看流程。

## What Changes

- 新增模型资产库主视图：在模型入口的主区域提供高保真网格浏览、顶部筛选/排序/密度/刷新/导入/选择/打开工具栏、右侧选中模型详情面板，并尽可能还原用户确认的示例图视觉与交互结构。
- 新增视觉验收基线：将示例图拆解为三栏比例、工具栏顺序、卡片结构、详情面板、滚动增量加载边界和响应式截图检查，同时视觉主题必须遵循项目现有 Apple 毛玻璃设计规范与深浅色模式适配。
- 将模型从“仅扫描 `outputs/*.ply` 的生成结果列表”升级为“模型资产”：支持 PLY、SPZ、SPLAT、RAD 等格式的统一索引、游标增量加载、筛选、排序、选择、下载、导出、删除和查看。
- 支持本机导入模型文件、批量上传模型文件，以及局域网已授权设备上传模型文件到当前工作目录的受控模型资产库。
- 支持为导入模型生成和缓存预览图：项目生成模型优先复用输入图片或源视频帧，外部导入模型通过浏览器端 Spark/Three.js 离屏渲染生成封面，并允许失败时使用稳定占位。
- 支持用户手动编辑模型资产资料，包括显示名称、标签、备注和封面；编辑内容不改变底层模型源文件路径。
- 保留现有生成流程、视频重建流程、Viewer 加载能力和下载/导出能力；旧 `/api/gallery` 等接口在过渡期保持兼容。
- 不包含：修改 `ml-sharp/` 上游代码；重写 Legacy `templates/index.html`；引入数据库、ORM、CSS-in-JS、Tailwind 或新的重型后端渲染服务；在第一阶段实现外部模型目录“引用型相册”或模型跨相册/集合管理（本次以复制导入到当前 workspace 的统一受控资产库为主）。

## Capabilities

### New Capabilities

- `model-asset-library`: 定义模型资产索引、模型导入、主视图网格浏览、选中详情、封面生成、资料编辑与模型操作的用户可见行为。

### Modified Capabilities

- `model-gallery-smoothness`: 将大模型集合的主要浏览体验从侧栏列表扩展到主模型资产库，继续要求大数量模型下保持响应、稳定缩略图状态和选择一致性。
- `lan-access-control`: 将模型导入、模型资料编辑、模型封面写入等新增私有端点纳入局域网门禁，并复用现有“允许远程生成”写入权限矩阵。

## Impact

- 前端：`frontend/src/App.tsx`、`frontend/src/components/gallery/`、`frontend/src/components/layout/Sidebar/`、`frontend/src/hooks/`、`frontend/src/store/useAppStore.ts`、`frontend/src/api/`、`frontend/src/types/`、`frontend/src/i18n/en.json`、`frontend/src/i18n/zh.json`。
- 后端：`backend/routes/gallery.py` 或新增模型资产路由、`backend/services/model_gallery.py` 或新增模型资产服务、`backend/paths.py`、`backend/services/static_files.py`、`backend/security/access_control.py`、`tests/`。
- 数据与文件：当前 workspace 下新增模型资产索引和导入模型/缩略图缓存；兼容既有 `outputs/*.ply/.spz`、`inputs/.thumbnails/` 与 `.meta.json` sidecar。
- API：新增模型资产列表、导入、资料编辑、封面保存/刷新、详情、删除等 `/api/` 端点；旧模型列表接口保持可用或通过兼容层返回。
- 测试：新增后端 route map、权限矩阵、路径安全、导入文件校验、索引兼容、缩略图缓存契约；前端至少覆盖关键纯函数和组件状态路径，人工或 Playwright 验证桌面/移动响应式布局与高保真还原。
