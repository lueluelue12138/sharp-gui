# 后端开发规范

## 架构概述

后端是一个 **模块化 Flask 应用**。`app.py` 只作为兼容入口保留：`from app import app` 可导入 Flask 实例，`python app.py` 会调用 `backend.server.run_server(app)` 启动服务。业务代码位于 `backend/` 包中：

1. **App Factory** — `backend/app_factory.py` 创建 Flask app、初始化 `PathContext`、注册安全 hooks 与 routes、挂载 `TaskManager`。
2. **运行时与配置** — `backend/runtime.py` 处理环境变量、verbose 日志、Sharp 命令/设备解析；`backend/config.py` 处理 `config.json` 与 access-control normalize；`backend/paths.py` 派生 workspace 相关路径。
3. **安全层** — `backend/security/access_control.py` 集中维护 Public / Unlocked / Owner / Conditional 权限矩阵；`backend/security/hooks.py` 注册 `before_request` / `after_request`。
4. **路由层** — `backend/routes/*` 按 API 域拆分，只处理 Flask request/response。
5. **服务层** — `backend/services/*` 承载模型图库、本地媒体图库、相册上传、任务队列、导出 HTML、静态文件解析和文件夹选择等可复用逻辑。
6. **任务队列** — `backend/services/task_queue.py` 的 `TaskManager` 持有 queue/status/lock/running processes。默认 app import 不启动 worker；只有服务运行入口显式启动，且启动操作幂等。
7. **更新管理器** — 专用 service 只管理安装身份、可信目标、兼容 gate、操作锁和持久化阶段；`create_app()`/模块导入只允许读取本地状态，不得联网、拉取 Git 或启动 updater 线程。

---

## API 端点清单

### LAN access-control tiers

- **Public**: `/`, React assets/root static files, `/api/auth/status`, `/api/auth/login`.
- **Unlocked**: valid HttpOnly access session or localhost owner. Covers gallery/model-asset/task reads, model/photo previews, downloads, exports, photo album reads, sanitized current update status, and `/files/*`.
- **Owner**: real localhost request with allowed Host. Covers settings writes, folder management, deletes, restart, batch conversion, task cancel, access-control management, and update checks/applies.
- **Conditional**: `/api/generate`, `/api/photo-conversions`, model asset imports/profile writes/cover writes are Owner by default; when `access_control.enabled=true` and `access_control.allow_remote_generation=true`, Unlocked remote devices may submit them.

When `access_control.enabled=false`, private read resources fall back to the old open LAN browsing behavior, but Owner endpoints must still enforce real localhost access. Disabling the gate must not make delete, settings, restart, folder management, batch conversion, or task cancellation remote-accessible.

Do not grant owner permissions from `X-Forwarded-For`, `Forwarded`, `X-Real-IP`, or other client-controlled headers. New private endpoints must be added to `get_required_access_level()` in `backend/security/access_control.py`; unknown `/api/*` and `/files/*` requests should remain Unlocked by default.

| 方法 | 路径 | 功能 | 权限 |
|------|------|------|------|
| GET | `/api/auth/status` | 认证状态、owner 状态和门禁配置摘要 | Public |
| POST | `/api/auth/login` | 使用访问码创建 HttpOnly Cookie 会话 | Public |
| POST | `/api/auth/logout` | 清除当前设备会话 | Unlocked |
| POST | `/api/auth/access-code` | 设置或修改访问码 | Owner |
| POST | `/api/auth/revoke` | 撤销所有远程会话 | Owner |
| POST | `/api/auth/settings` | 更新门禁启用状态、会话天数、远程生成等配置 | Owner |
| GET | `/api/gallery` | 获取作品列表 | Unlocked |
| POST | `/api/generate` | 上传图片生成模型 | Owner / Conditional |
| GET | `/api/tasks` | 获取任务队列状态 | Unlocked |
| POST | `/api/task/<id>/cancel` | 取消任务 | Owner |
| DELETE | `/api/delete/<id>` | 删除作品 | Owner |
| GET | `/api/download/<id>` | 下载模型文件（支持 `?format=spz|ply`） | Unlocked |
| GET | `/api/original/<id>` | 获取上传原图（inline 预览或附件下载） | Unlocked |
| GET | `/api/thumbnail/<id>` | 获取或按需修复缩略图 | Unlocked |
| POST | `/api/convert-all` | 批量将既有 PLY 转换为 SPZ | Owner |
| GET | `/api/settings` | 读取设置 | Unlocked |
| POST | `/api/settings` | 写入设置 | Owner |
| POST | `/api/restart` | 重启服务器 | Owner |
| GET | `/api/updates/status` | 读取脱敏后的安装版本、能力和更新阶段 | Unlocked |
| POST | `/api/updates/check` | 按 Stable/Latest 解析并缓存受信任目标 | Owner |
| POST | `/api/updates/apply` | 应用后端刚验证过的精确目标提交并重启 | Owner |
| POST | `/api/browse-folder` | 原生文件夹选择 | Owner |
| GET | `/api/export/<id>` | 导出为 Spark 2.0 独立 HTML（支持 `?format=spz|ply`） | Unlocked |
| GET | `/api/photo-albums` | 获取本地媒体相册列表 | Unlocked |
| POST | `/api/photo-albums` | 新增本地媒体相册目录配置 | Owner |
| DELETE | `/api/photo-albums/<album_id>` | 移除本地媒体相册配置，不删除原始文件 | Owner |
| POST | `/api/photo-albums/<album_id>/scan` | 重新扫描本地媒体相册 | Owner |
| GET | `/api/photo-albums/<album_id>/photos` | 分页获取相册媒体，支持 `type=all|photo|video` 与时间/名称/大小排序 | Unlocked |
| POST | `/api/photo-albums/<album_id>/uploads` | 上传照片到当前相册目录 | Unlocked when gate enabled / Owner when gate disabled |
| GET | `/api/photo-thumbnail/<photo_id>` | 获取或按需生成照片缩略图 | Unlocked |
| GET | `/api/photo-original/<photo_id>` | 获取照片原图（inline 或 `?download=1` 附件） | Unlocked |
| GET | `/api/video-poster/<video_id>` | 获取或按需生成视频 poster | Unlocked |
| GET | `/api/video-original/<video_id>` | 获取视频原文件（inline 或 `?download=1` 附件，支持 Range） | Unlocked |
| GET | `/api/video-play/<video_id>/<play_token>/<path:filename>` | 使用短期签名票据播放视频原文件（支持 Range） | Public when valid token / otherwise Unlocked |
| POST | `/api/photo-downloads` | 打包下载选中的照片/视频原文件 ZIP | Unlocked |
| POST | `/api/photo-conversions` | 将单张/多张照片加入现有 3D 生成队列 | Owner / Conditional |
| POST | `/api/video-reconstructions` | 从本地相册视频创建视频 3DGS 重建任务 | Owner / Conditional |
| POST | `/api/video-reconstructions/upload` | 从拖入/上传的视频文件创建视频 3DGS 重建任务 | Owner / Conditional |
| GET | `/api/video-reconstructions/status` | 读取视频重建默认配置与依赖诊断状态，支持 `?refresh=1` 触发后台重扫 | Unlocked |
| GET | `/api/gallery/<item_id>/source-video` | 预览视频重建模型对应的原视频（来自 sidecar 元数据解析） | Unlocked |
| GET | `/api/model-assets` | 游标式获取模型资产列表，支持来源/格式/标签筛选、排序和计数 | Unlocked |
| GET | `/api/model-assets/<asset_id>` | 获取模型资产详情、可用格式、封面、源媒体和可解析元数据 | Unlocked |
| POST | `/api/model-assets/import` | 导入 `.ply/.spz/.splat/.rad` 模型到受控资产目录 | Owner / Conditional |
| POST / PATCH | `/api/model-assets/<asset_id>` | 更新模型资产名称、标签、备注等用户编辑信息；POST 为现有前端兼容方法 | Owner / Conditional |
| POST | `/api/model-assets/<asset_id>/cover` | 上传或更新模型资产封面 | Owner / Conditional |
| POST | `/api/model-assets/<asset_id>/cover/refresh` | 重新生成或刷新模型资产封面状态 | Owner / Conditional |
| GET | `/api/model-assets/<asset_id>/download` | 按默认格式或指定格式下载模型资产文件 | Unlocked |
| DELETE | `/api/model-assets/<asset_id>` | 删除模型资产索引项和受控导入文件；生成结果删除仍遵守原模型删除策略 | Owner |

### 新增端点规则

1. **路由前缀**：必须使用 `/api/` 前缀
2. **返回格式**：统一返回 JSON（`jsonify()`）
3. **错误响应**：统一至少返回 `{"error": "描述"}` + 对应 HTTP 状态码；模型资产及新增结构化端点还应提供 `{"code": "stable_error_code"}`。批量接口可附带逐项 `failed[]`，但全批失败时仍必须保留顶层 `error` / `code`，不能让客户端只得到通用 HTTP 状态文本
4. **路由位置**：在 `backend/routes/` 选择对应业务模块；必要时新增 `backend/services/` 服务函数，避免把大段业务流程写在 route 中
5. **权限控制**：在 `backend/security/access_control.py` 的 `get_required_access_level()` 中明确 Public / Unlocked / Owner / Conditional；owner 判断只能使用真实 `request.remote_addr` + 允许的 Host，不能相信转发头
6. **测试覆盖**：新增或调整 pytest，至少覆盖 route map、权限矩阵或相关服务纯函数

```python
# ✅ 标准路由模式
bp = Blueprint("my_feature", __name__)

@bp.route('/api/my-endpoint', methods=['GET'])
def api_my_endpoint():
    """获取某某数据"""
    try:
        result = my_service.do_something()
        return jsonify({"data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

## 任务队列系统

### 架构

```python
task_manager = current_app.config["TASK_MANAGER"]
task_info = task_manager.enqueue_file(input_path, filename)
```

任务队列通过 `kind` 分发不同生成流程：

| kind | 说明 |
|------|------|
| `image_sharp` 或缺省 | 现有图片 / 照片转 3D，调用 `sharp predict` |
| `video_3dgs` | 视频重建，调用 `backend.services.video_reconstruction.run_video_reconstruction_task()` |

### 任务生命周期

```
pending → running → processing → completed
                  ↘ failed
                  ↘ cancelled
```

### 关键实现

- **Worker 线程**：`TaskManager.start_workers()` 启动后台线程，从队列取任务，按 `kind` 调用图片 SHARP 或视频重建处理函数
- **进度解析**：实时读取 subprocess 的 stdout，解析进度阶段（downloading → loading → preprocessing → inference → postprocessing → saving）
- **取消机制**：`process.terminate()` 终止子进程
- **自动清理**：已完成任务 1 小时后自动从内存中移除（`TASK_RETENTION_SECONDS`）
- **导入无副作用**：`create_app()` 和 `from app import app` 默认不启动 worker/cleanup 线程，便于 pytest 和工具导入
- **工作区互斥**：服务进程在 `TaskManager.start_workers()` 中取得 `{workspace}/.sharp-gui.lock` 的操作系统级独占锁；只有成功持锁后才能执行图片任务协调和视频残留清理
- **切换预检**：Settings 保存不同的 `workspace_folder` 前必须短暂取得并释放目标工作区锁；占用时返回 `409 workspace_in_use`，不得修改配置或触发重启

视频重建任务的阶段应保持用户可读，不要求前端阅读完整日志即可知道状态：`video_prepare`、`video_extract_frames`、`video_estimate_geometry`、`video_train_splats`、`video_export_splats`、`video_cleanup_splats`、`video_convert_spz`、`completed` / `failed` / `cancelled`。

### 线程安全

修改任务状态时必须通过 `TaskManager` API 或其内部 `task_lock`：

```python
with task_manager.task_lock:
    task_manager.task_status[task_id] = {
        'status': 'running',
        'progress': 0,
        'stage': 'loading'
    }
```

---

## 文件路径处理

### 工作目录结构

```python
workspace_folder = config.get('workspace_folder', BASE_DIR)
input_folder = os.path.join(workspace_folder, 'inputs')
output_folder = os.path.join(workspace_folder, 'outputs')
thumbnail_folder = os.path.join(input_folder, '.thumbnails')
photo_gallery_cache_folder = os.path.join(workspace_folder, '.photo-gallery-cache')
photo_catalog_file = os.path.join(photo_gallery_cache_folder, 'catalog.json')
photo_album_index_folder = os.path.join(photo_gallery_cache_folder, 'albums')
photo_thumbnail_folder = os.path.join(photo_gallery_cache_folder, 'thumbnails')
video_poster_folder = os.path.join(photo_gallery_cache_folder, 'video-posters')
model_asset_folder = os.path.join(workspace_folder, 'model-assets')
model_asset_import_folder = os.path.join(model_asset_folder, 'imports')
model_asset_thumbnail_folder = os.path.join(model_asset_folder, 'thumbnails')
model_asset_library_folder = os.path.join(workspace_folder, '.model-asset-library')
model_asset_index_file = os.path.join(model_asset_library_folder, 'index.json')
video_reconstruction_folder = os.path.join(workspace_folder, '.video-reconstruction')
video_reconstruction_jobs_folder = os.path.join(video_reconstruction_folder, 'jobs')
video_reconstruction_uploads_folder = os.path.join(video_reconstruction_folder, 'uploads')
```

### 规则

- 使用 `os.path` 构造绝对路径，不使用字符串拼接
- `secure_filename()` 处理用户上传的文件名
- 新增持久化目录时，先归类为 workspace 绑定用户数据、项目根配置/密钥、依赖目录或构建缓存；workspace 绑定数据必须由 `PathContext` 或基于 `PathContext.workspace_folder` 的 helper 派生，不得硬编码在项目根
- 新增运行时目录必须同步更新 `.agents/rules/project-overview.md` 的“用户数据与运行时目录总表”、README 工作目录说明和 `.gitignore`
- 缩略图存储在 `{workspace}/inputs/.thumbnails/`
- 模型资产导入文件存储在 `{workspace}/model-assets/imports/`，封面缓存存储在 `{workspace}/model-assets/thumbnails/`，索引和用户编辑信息存储在 `{workspace}/.model-asset-library/index.json`
- 这些模型资产路径必须始终由当前 `PathContext.workspace_folder` 派生；Settings 切换工作目录后需要重启服务重建 `PathContext`，不得把模型资产索引或导入目录保存在项目根的全局位置
- 本地媒体图库 catalog、每相册索引、照片缩略图、视频 poster 和批量下载临时 ZIP 存储在 `{workspace}/.photo-gallery-cache/`
- 视频重建中间文件、Nerfstudio 数据、日志存储在 `{workspace}/.video-reconstruction/jobs/`，拖入视频上传缓存存储在 `{workspace}/.video-reconstruction/uploads/`
- 输出目录同时保留 `.ply` 原始模型和自动生成的 `.spz` 紧凑模型
- 视频重建结果额外写入 `outputs/<model-id>.meta.json`，记录来源视频、模式、质量、引擎和受控源视频引用；JSON 响应不得暴露 `source_video_path`
- 配置文件 `config.json` 位于项目根目录（`BASE_DIR`），不随 workspace 切换；证书、私钥、日志和依赖目录同样是项目根运行时/部署状态，不得通过 `/files/*` 暴露
- `.sharp-gui-update/` 是项目根安装状态，只能保存原子更新阶段、最近检查的目标、操作锁与有界诊断；`.sharp-gui-tools/` 是便携包工具目录。两者都不随 workspace 切换，不得通过 `/files/*` 暴露，也不得被代码 checkout/失败恢复清理
- 本地媒体图库 API 只接受 photo/media/video id，不接受任意绝对路径；后端必须从索引反查原始文件并再次校验 root
- 模型资产 API 只接受 asset id 与受支持扩展名，不接受前端传入的服务器绝对路径；导入、封面和下载路径必须从资产索引或受控目录反查并再次校验 root
- 模型资产的受控根需要两级校验：先确认 `imports/`、`thumbnails/`、`outputs/` 等根的真实路径仍位于真实 workspace 内，再确认目标真实路径位于对应受控根内；根目录本身是 symlink、junction 或其它 reparse point 且指向 workspace 外时也必须安全失败
- 本地媒体图库正常读路径不得依赖全局可变索引文件：相册列表读 `catalog.json`，相册分页/筛选/排序读 `albums/<album_id>.json`，媒体解析通过可解析 media id 定位相册索引
- 视频响应优先使用 `send_from_directory(..., conditional=True, download_name=...)`，交给 Werkzeug 生成兼容中文文件名的响应头，不要手写 `Content-Disposition`
- `/api/video-play/<video_id>/<play_token>/<filename>` 的 token 只授权短期 inline 播放，不能绕过 `/api/video-original/<video_id>?download=1` 的 Unlocked 下载权限
- 删除相册时必须清理该相册媒体 ID 对应的照片缩略图和视频 poster；不得删除用户相册目录中的原始文件
- 批量下载生成的 `photo-gallery-*.zip` 是临时文件：响应关闭时尝试删除，创建新 ZIP 前清理过期残留，不能误删索引、缩略图或 poster
- 删除视频重建模型时可删除 `.ply/.spz`、同名 `.meta.json`、缩略图和受控上传缓存；如果来源是本地相册视频，必须保持原视频只读且绝不删除

---

## 配置管理

### config.json 结构

```json
{
  "workspace_folder": "/path/to/workspace",
  "model_format": "spz",
  "photo_gallery_roots_by_workspace": {
    "/path/to/workspace": [
      {
        "id": "stable-root-id",
        "name": "Screenshots",
        "path": "D:/Pictures/Screenshots",
        "recursive": true,
        "enabled": true
      }
    ]
  },
  "access_control": {
    "enabled": false,
    "session_days": 30,
    "allow_remote_generation": false,
    "lan_bind_enabled": true
  },
  "video_reconstruction": {
    "default_quality": "high",
    "default_engine": "auto",
    "vram_budget": "12gb",
    "keep_intermediate": false
  }
}
```

`.sharp-gui.lock` 文件存在不代表工作区正在使用，判断必须以 `WorkspaceInstanceLock.acquire()` 的结果为准；不得通过删除锁文件绕过活跃实例。进程结束或服务停止后应释放锁，但锁文件本身可留在 workspace 中供下次复用。

### 兼容性

代码需兼容旧配置格式（`input_folder` / `output_folder`）到新格式（`workspace_folder`）的自动迁移。

`model_format` 控制前端默认查看和下载格式，当前有效值为 `spz` / `ply`。

`photo_gallery_roots_by_workspace` 控制本地媒体图库相册目录（历史命名保留 photo 前缀），**按工作目录分桶记忆**：以归一化后的工作目录路径（`os.path.normcase(os.path.realpath(...))`）为键，值为该工作目录下的相册列表。切换工作目录时只展示对应桶的相册，切回原目录即可恢复；这与模型列表绑定 `{workspace}/outputs` 的行为一致。

- 读：`get_photo_gallery_roots_for_config(config)` 取当前 `workspace_folder` 对应桶；`normalize_photo_album_roots()` 在其之上做规范化。
- 写：`set_photo_gallery_roots_for_config(config, roots)` 写入当前工作目录桶并清理旧字段。
- 迁移：旧配置使用顶层 `photo_gallery_roots` 数组，`migrate_photo_gallery_roots_config(config)` 会在应用启动（`app_factory`）和切换工作目录前（`settings` 路由）把它归档到当前工作目录的桶并移除顶层字段；缺省时按空数组处理，不影响旧配置启动。
- 切换工作目录的逻辑切勿直接清空相册；必须依赖分桶切换，否则会丢失其它工作目录已记忆的相册。

`access_control` 控制可选局域网门禁；缺省或 `enabled=false` 时读取资源保持旧的局域网开放行为，但 owner-only 端点仍必须限制真实 localhost。`lan_bind_enabled`（缺省 `true`）决定服务监听 `0.0.0.0`（局域网共享）还是 `127.0.0.1`（仅本机），修改后需重启生效。

`video_reconstruction` 控制视频重建默认值；缺省时由 `normalize_video_reconstruction_config()` 补齐。当前已端到端验证的平台是 Windows + NVIDIA RTX 5070 Ti Laptop GPU 12GB，默认 `high` 档应优先服务该硬件，不要把未验证平台写成已支持。

## 视频 3DGS 重建服务

稳定路线位于 `backend/services/video_reconstruction.py`，路由位于 `backend/routes/video_reconstruction.py`。当前实现约定：

- `POST /api/video-reconstructions` 只接受本地相册 video id；后端必须通过相册索引反查路径并校验真实路径仍在相册 root 内。
- `POST /api/video-reconstructions/upload` 只接受单个受支持视频文件，并保存到 `.video-reconstruction/uploads/` 这类受控工作区缓存。
- 默认输出名使用源视频文件名 stem；只在冲突时追加唯一后缀，不自动追加质量、帧数或 cleanup 标记。
- 依赖检测使用进程级缓存：`app_factory.create_app()` 调用后台 warmup；`/api/video-reconstructions/status?refresh=1` 可触发后台重扫；普通任务创建读取缓存，检测中时返回 `video_reconstruction_dependencies_checking`，不得同步阻塞页面。
- 子进程命令必须使用列表参数，不拼接 shell 字符串；日志默认只输出关键阶段、命令名、return code 和失败摘要，完整外部工具输出只在 `SHARP_LOG_LEVEL=DEBUG` 或 verbose 模式下显示。
- OOM、缺依赖、非法选项、输出缺失、SPZ 失败、取消等错误应转换为稳定错误码，前端用 i18n 展示，不把原始堆栈作为主 UI 文案。
- `auto` / `object` 模式默认尝试 focused cleanup；如果清理会删除过多几何，必须回退原始导出并记录原因；`environment` 模式不做主体裁剪。
- 成功后调用现有模型图库逻辑生成视频封面缩略图、写 sidecar 元数据并刷新模型列表；源视频预览通过 `/api/gallery/<item_id>/source-video` 解析 sidecar，不能直接把绝对路径传给前端。

---

## CORS 处理

通过 `after_request` 钩子手动添加。启用 Cookie 会话后，不允许继续对凭证请求返回 `Access-Control-Allow-Origin: *`；只能回显通过 `is_origin_allowed()` 校验的 origin，并设置 `Access-Control-Allow-Credentials: true`：

```python
@app.after_request
def after_request(response):
    origin = request.headers.get('Origin')
    if origin and is_origin_allowed(origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers.add('Vary', 'Origin')
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response
```

不使用 `flask-cors` 扩展。

---

## HTTPS 与监听绑定

- 自动检测项目根目录下的 `cert.pem` / `key.pem`
- 有证书时使用 `ssl_context`；无证书时 fallback 到 HTTP（此时访问码/会话明文传输，前端会提示）
- 证书由 `tools/generate_cert.py` 生成
- **监听地址**由 `access_control.lan_bind_enabled` 决定：`true` → `0.0.0.0`（局域网共享），`false` → `127.0.0.1`（仅本机）。环境变量 `SHARP_BIND_HOST` 可覆盖。修改该开关需重启服务生效（前端保存后自动重启）。
- **调试模式默认关闭**：`app.run` 默认 `debug=False`、`use_debugger=False`、`use_reloader=False`，避免向客户端泄露堆栈与 RCE 风险，并防止 Werkzeug reloader 的 socket 继承机制干扰 `/api/restart` 的重新绑定（见下方重启说明）。仅 `SHARP_DEBUG=1` 时三者同时开启，且只应在本机排障使用。
- **`/api/restart` 的重新绑定机制**：`do_restart` 使用 `os.execv` 替换进程映像来实现重启，这样可以读取最新的 `config.json`（包括切换后的 `lan_bind_enabled`）。重启前必须调用 `os.closerange(3, max_fds)` 关闭所有继承的 FD（尤其是监听 socket），否则 execv 后新映像尝试重新 bind 时会遇到 `Address already in use` 而崩溃，导致绑定"假切换"。`use_reloader=False` 也是必要条件：reloader 开启时父进程持有 socket 并通过 `WERKZEUG_SERVER_FD` 传给子进程，无法通过 `closerange` 干净释放。

## 静态文件服务（/files/*）

`/files/<path>` 由 `serve_files` 提供，**收敛到白名单服务根**，不再以 `BASE_DIR` 为默认根：

- 仅允许 `ALLOWED_FILE_SERVE_ROOTS`（`outputs/` 模型、`inputs/.thumbnails/` 历史缩略图、`model-assets/imports/` 导入模型与 `model-assets/thumbnails/` 封面缓存）内的文件。
- 解析后的真实路径用 `is_real_path_inside` 校验（基于 `realpath` + `commonpath`），落在白名单外、相对穿越、绝对路径或符号链接逃逸一律 404。
- 命中敏感清单（`config.json`、`*.pem`、`*.key`、`app.py`、`.env` 等）一律 404，**不区分“不存在”与“被禁”**以避免信息泄露。
- 该校验独立于门禁开关：即便 `access_control.enabled=false`，敏感系统文件也不会通过 `/files/*` 暴露。
- 新增需要对外提供的静态目录时，必须显式加入 `ALLOWED_FILE_SERVE_ROOTS`，不要放宽回 `BASE_DIR`；`.model-asset-library/` 索引目录不得加入静态白名单。

---

## 外部工具脚本

| 文件 | 功能 | 调用方式 |
|------|------|----------|
| `tools/detect_cuda.py` | 解析 `nvidia-smi` 获取 CUDA 版本 | 安装阶段 |
| `tools/download_model.py` | 多源下载模型（HF → HF 镜像 → Apple CDN）| 安装阶段 |
| `tools/generate_cert.py` | 跨平台生成自签名 SSL 证书 | 安装阶段 / 手动 |
| `tools/install_torch.py` | 根据 CPU/CUDA 环境安装兼容 PyTorch | 安装阶段 |
| `tools/update.py` | Stable/Latest 安全检查、外部事务应用与失败恢复 | Settings / `update.sh` / `update.bat` |

---

## 自更新服务与事务边界

- `GET /api/updates/status` 只能返回脱敏的版本、commit、能力、兼容性和操作阶段；不得返回绝对路径、Git 命令、凭据、原始异常栈或远端响应正文。check/apply 都是 owner-only mutation，集中权限矩阵和 route 内 `g.is_owner` 纵深检查必须同时存在。
- Stable 从规范仓库 Git refs 选择版本号最高的正式 `vX.Y.Z` 标签；Latest 解析 `main`。apply 只接受通道并使用服务端最近检查的 exact SHA，重新校验仓库、时效和 `update-manifest.json`；绝不接受客户端 URL、repo、branch、tag、SHA 或命令作为执行目标。
- 检查只使用 Git 的 `ls-remote` / exact fetch，不维护 GitHub REST、ETag 或 stale cache fallback；网络失败必须明确报错，不能伪装成“已是最新”，也不得以未验证 ZIP 覆盖作为 fallback。
- apply 在任何文件 mutation 前必须取得安装级独占锁，并拒绝：待处理/运行/processing 的生成任务、另一个更新、dirty tracked worktree、源码安装处于非 `main` 开发分支、过期目标、manifest/runtime revision 不兼容或缺少 built frontend。忽略/未跟踪的用户与运行时目录不应被误判为 dirty。
- Flask 进程只负责校验、持久化意图和启动外部 helper。helper 必须等待 serving process 边界后，记录 previous SHA，fetch exact target，再次检查兼容性，更新受管文件并执行 compile/import/frontend/package health checks；成功后原子记录 current/previous SHA 并重启。
- checkout、验证或启动前健康检查失败时，helper 必须自动 reset 到 previous SHA、验证旧版本并重启，最终状态明确为 rolled back failure。非终态操作在下次启动时必须按实际 HEAD 与 previous/target SHA 对账恢复；在恢复完成前不得接受新 mutation。
- Git 调用使用列表参数、非交互环境、固定 canonical origin 和绝对 executable。便携包优先 `.sharp-gui-tools/git/cmd/git.exe`，不得修改全局 PATH/Git 配置或静默改用 PATH 中同名程序。
- 代码 checkout 只能管理应用源码；嵌入式 Python/PyTorch/CUDA、`.video-reconstruction-env/`、模型/缓存、workspace、配置/证书/日志、便携包元数据、`.sharp-gui-update/` 和 `.sharp-gui-tools/` 必须保持在受管 checkout 之外。runtime revision 不一致时必须要求完整包，不能由 updater 原地升级这些大型环境。
- 普通 `backend/`、`frontend/src/` 与 `frontend/dist/` 文件的新增、删除、重命名和重构不要求提高 runtime revision；依赖清单、安装器或便携包构建脚本变化时，CI 要求提高 `portableRuntimeRevision` 并发布新版完整便携包。

---

## 安全要点

> 虽然是个人项目 + 局域网使用场景，但以下基础防线仍需遵守：

### 文件上传

- **必须** 使用 `secure_filename()` 清理用户上传的文件名
- **必须** 校验文件扩展名白名单（`.jpg`, `.jpeg`, `.png`, `.webp`）
- **禁止** 直接拼接用户输入到文件路径（防路径遍历）
- 模型资产导入只允许 `.ply`, `.spz`, `.splat`, `.rad`；当前上限为单批 64 个文件、单文件 2 GiB、整批 10 GiB。除服务层流式计数外，还必须设置请求级总大小上限，避免 Werkzeug 在进入 service 前先解析无界 multipart；失败或索引提交失败时清理本批未提交文件
- 模型资产导入应保留规范化后的原始 basename 作为展示/下载名称，再为物理存储分配安全唯一名；不要用 `secure_filename()` 的 ASCII 结果覆盖用户的 Unicode 名称。物理文件名的分配与落盘必须具备并发原子性，优先使用 UUID 名或在同一锁域内完成保留
- 模型资产封面上传只允许受支持图片格式，当前单文件上限为 10 MiB；必须校验实际图片格式、像素维度和目标路径，保存到 `{workspace}/model-assets/thumbnails/`，不得覆盖索引目录或原始模型文件

```python
# ✅ 正确
from werkzeug.utils import secure_filename
filename = secure_filename(uploaded_file.filename)
full_path = os.path.join(input_folder, filename)

# ❌ 危险 — 用户可构造 ../../etc/passwd
full_path = os.path.join(input_folder, request.form['filename'])
```

### 路径构造

- 使用 `os.path.join()` 而非字符串拼接
- 涉及用户输入或索引反查的路径，统一使用 `os.path.abspath()`、`os.path.realpath()`、`os.path.commonpath()` 和平台大小写归一化验证；优先复用 `is_real_path_inside()`，不要使用容易被同前缀目录和符号链接绕过的 `startswith()`：

```python
resolved = os.path.realpath(os.path.abspath(os.path.join(workspace, user_input)))
if not is_real_path_inside(resolved, workspace):
    return jsonify({"error": "Invalid path"}), 403
```

### 本地媒体图库路径安全

- 相册新增、删除、重新扫描这类配置写操作必须仅允许 localhost。
- 原图、缩略图、视频 poster、视频播放、下载、转换接口必须通过 media/photo/video id 解析，不能接受前端传来的绝对路径。
- 解析 media id 后必须使用 `os.path.abspath()`、`os.path.realpath()`、`os.path.commonpath()` 和平台大小写归一化确认文件仍在配置 root 内。
- `media_id` 应内嵌可解析的 `album_id`，不要再引入全局 media lookup 表；解析失败、相册不存在、索引缺失或真实文件不在 root 内时必须返回安全失败。
- Windows 需要避免跨盘符 `commonpath` 抛错导致接口 500；Linux/macOS 需要避免符号链接逃逸相册 root。
- 原图/视频响应优先使用 `send_from_directory(..., download_name=...)` 交给 Werkzeug 生成兼容的 `Content-Disposition`，不要手写包含中文的 header；视频 inline 播放必须启用 `conditional=True` 以支持 Range seek。
- 视频重建 source-video 预览同样使用受控解析 + `send_from_directory(..., conditional=True, download_name=...)`，不得绕过门禁和路径校验。
- 路径式视频播放 token 必须绑定 video id、过期时间和 access-control session version；修改访问码或撤销会话后旧 token 失效。token 只用于播放，不用于附件下载。
- `POST /api/photo-albums/<album_id>/uploads` 属于本地媒体图库服务：route 层只读取 multipart `file` 列表并封装响应，`services/photo_gallery.py` 必须负责相册存在/启用/目录可用检查、`PHOTO_MAX_UPLOAD_BATCH`、`secure_filename()`、扩展名白名单、唯一命名、真实路径 root 约束、Pillow `verify()`、失败清理与上传后扫描刷新。
- 照片相册上传权限必须在集中矩阵中显式列出：门禁开启且远程已解锁时允许，门禁关闭或未解锁时远程拒绝。

### 本地媒体图库索引与性能

- 应用启动和普通 `/api/photo-albums` 列表请求不得扫描所有相册目录；相册摘要通过 `catalog.json` 返回，缺索引时返回待索引/扫描状态并安排低优先级 bootstrap。
- `GET /api/photo-albums/<album_id>/photos` 的分页、排序、类型筛选应在已存在的每相册索引上完成；暖索引路径不得调用 `os.walk`、不得逐文件 `stat`、不得重写全量 catalog。
- 只有显式扫描、首次建立相册索引、相册上传后刷新等写路径可以遍历相册目录；遍历时使用相册级锁，不能长时间持有全局锁。
- 写 JSON 缓存使用原子替换，内容未变时不触盘；避免对所有相册共用一个大 JSON 并在每次分页/排序时全量重写。
- 旧全局 `index.json` 只能作为迁移源。迁移应一次性折算 catalog 并归档旧索引；旧索引不存在后，不得回退读取所有 `albums/*.json` 来重建全局索引。
- 视频元数据和图片尺寸复用是性能优化，不是正确性前提；归档后首扫重新计算可接受，但结果必须正确并可继续按需生成缩略图/poster。
- 清理图库缓存只能删除 `.photo-gallery-cache` 内的 catalog、每相册索引、缩略图、poster 和临时 ZIP，绝不能删除用户相册目录中的原始媒体。

### 模型资产库索引与性能

- 普通 `GET /api/model-assets` 应从 workspace 级摘要快照或增量索引使用稳定游标和固定批次返回结果；暖路径、后续游标页、筛选和排序不得同步 `os.listdir` / `os.walk` 完整 `outputs/`，也不得逐资产重复 `stat`、读取 sidecar 或生成封面。
- 首次迁移、显式刷新或冷启动可建立摘要；生成任务完成、导入、删除、资料和封面写入应增量更新或精确失效。列表读取应容忍文件并发出现/消失，单个资产的 `stat` / `open` 失败只能跳过或标记不可用，不能让整页 500。
- 筛选、排序和格式选择在资产摘要上完成；PLY/SPLAT 头部解析、SPZ/RAD 高级元数据读取只在详情请求或受控后台任务执行。游标只是响应分页协议，不能用“已分页”掩盖每个请求仍全量扫描的实现。
- `.model-asset-library/index.json` 是导入资产稳定 ID、物理文件映射和用户编辑信息的持久化真相源，不是可随意删除的缓存。只有 `missing` 状态可初始化空索引；`corrupt` / schema 非法状态必须保留并隔离原文件、返回稳定诊断或进入显式恢复，任何写操作都不得把它当空索引静默覆盖。
- 生成资产的文件派生摘要可从 `outputs/` 恢复，但生成资产的用户编辑和导入资产的稳定 ID、名称、资料不能仅由文件名无损重建。若提供“重建索引”，必须明确恢复范围和资料损失，并在用户确认前保持原索引与导入文件不变。
- 所有索引 read-modify-write 使用同一锁和临时文件原子替换。导入的唯一物理名分配、文件提交与索引提交必须形成并发安全事务；索引落盘失败应回滚本批新文件，不能留下 UI 无法管理的孤儿文件。
- 资料更新、封面上传/刷新和删除在提交前必须在同一临界区重新确认资产仍存在、来源类型和身份字段未变化；先读后长时间处理的旧快照不得在删除后复活幽灵索引项或孤立封面。
- 封面必须先写独立临时文件并完成大小、真实格式、像素和 Pillow 校验，再在锁内原子替换正式文件与索引。替换或恢复系统封面后应清理同 asset id 的旧 JPG/PNG/WebP 变体；失败上传必须保留原有效封面，共享旧记录不能被半成品覆盖。
- 删除只有在受控文件、封面和索引达到一致状态后才能返回成功；磁盘删除或索引写入失败应返回稳定错误并保留可恢复记录，不能吞掉异常后把资产从索引移除。删除生成资产仍应遵守原有 `outputs/` 策略，不能误删本地媒体图库原始文件或视频来源文件。
- 每次 list/detail/download/delete 最终使用文件前都要重新做真实路径 root 校验，生成文件也不能只依赖规范化 asset id。`outputs/` 内文件 symlink、受控根自身的 junction/reparse point 和跨盘符逃逸都必须拒绝。
- 源文件缺失或不可读时返回 `available=false`、`files=[]`、`formats=[]`、`default_open_url=null` 和 `download_url=null`；不得继续暴露指向不存在文件的打开或下载地址。
- 用户设置中的 PLY/SPZ 偏好由前端解析后显式传 `format`；后端未指定格式时仅使用兼容兜底顺序 `SPZ → PLY → SPLAT → RAD`。两者不得混写成索引中的“默认格式”。下载名使用用户展示名与已验证扩展名，并交给 Werkzeug `download_name` 生成 Unicode 兼容响应头。
- 详情字段中无法从文件或 sidecar 明确得到的点数、包围盒、坐标系、压缩、版本等信息应返回未知/空值，前端不得把占位字段显示成真实计算结果。

### 其他

- **仅 localhost 可写入**的端点需检查 `request.remote_addr`
- **局域网门禁**关闭时只放开私有读取资源，不得放开设置、删除、重启、目录管理、取消任务等 owner-only 操作
- **Owner 判断**只能信任真实连接地址和允许的 Host，不得使用 `X-Forwarded-For`、`Forwarded`、`X-Real-IP` 等客户端可控头
- **静态文件服务**只能从 `ALLOWED_FILE_SERVE_ROOTS` 白名单根提供，敏感文件（`config.json`、证书私钥、`app.py` 等）必须拒绝；该限制不随门禁开关放宽
- **调试模式**默认关闭，不向客户端返回堆栈、不暴露交互式调试器；仅 `SHARP_DEBUG=1` 本机排障时开启
- **反向代理**：若本机前置反向代理，所有请求 `remote_addr` 会变成 `127.0.0.1` 导致全员被判 owner；`allow_localhost_bypass` 目前只能改 `config.json`（无设置界面开关，需先设访问码），关闭后会同时取消本机 owner 身份从而禁用自更新，文档须一并说明该限制
- **subprocess 调用**使用列表参数（非字符串拼接），避免命令注入
- **不要**在 JSON 响应中暴露服务器绝对路径或堆栈信息

### 后端日志

- 默认 `SHARP_LOG_LEVEL=INFO` 只输出关键业务阶段和失败摘要，避免 HTTP 轮询、缩略图请求和外部工具逐行输出刷屏。
- `SHARP_HTTP_LOGS=1` 才输出 Werkzeug HTTP 请求日志。
- 排查视频重建失败时优先使用 `run.bat --verbose` 或设置 `SHARP_LOG_LEVEL=DEBUG`，此时可看到完整命令、外部工具输出和 traceback。
- 失败日志可以详细，成功路径日志必须克制：入队、阶段切换、命令开始/结束、最终完成/失败即可。

### 后续清理 TODO

- 本次模块化迁移暂时保留部分路由内部重复 owner 检查，作为集中 hook 之外的纵深防御。后续新需求或专门清理任务中，可以在 pytest 覆盖稳定后统一梳理这些重复检查，决定哪些删除、哪些保留。

---

## 编码风格

- **函数命名**：`snake_case`（如 `load_config`, `ply_to_splat`）
- **常量命名**：`UPPER_CASE`（如 `TASK_RETENTION_SECONDS`）
- **注释语言**：中文 docstring + 中文行内注释
- **日志**：`print()` + emoji 前缀（如 `🔄 Processing task`、`✅ Task completed`）
- **错误处理**：`try/except Exception as e`，避免裸 `except:`
- **类型注解**：当前无强制要求，鼓励在新代码中添加
- **导入风格**：标准库可合并一行（`import os, sys, json`），三方库分开导入
