# 测试规范

## 现状

项目已正式引入 **后端 pytest**：

- 后端测试位于项目根目录 `tests/`。
- 开发测试依赖记录在 `requirements-dev.txt`，普通一键安装/运行脚本不强制安装 pytest。
- `create_app()` 与 `from app import app` 默认不启动后台 worker，测试可安全创建 Flask test client。
- 前端仍未正式引入 Vitest / Testing Library；新增前端复杂逻辑时可按推荐框架补充。

---

## 测试目标

鼓励为新功能添加测试，优先覆盖以下关键路径：

| 优先级 | 覆盖范围 | 说明 |
|--------|----------|------|
| 🔴 高 | 后端 API 端点 | 确保 `/api/*` 请求/响应正确 |
| 🔴 高 | 后端安全边界 | LAN 门禁、owner-only、远程生成、相册上传、静态文件白名单 |
| 🔴 高 | 自更新事务与便携隔离 | exact commit、兼容 gate、数据/运行时保留、失败回滚、无系统 Git/Python |
| 🔴 高 | 工具函数 | `utils/format.ts`, `utils/camera.ts`, `ply_to_splat()` 等纯函数 |
| 🟡 中 | 前端组件 | 关键交互组件（Button, Modal, GalleryItem） |
| 🟡 中 | Zustand Store | Action 逻辑正确性 |
| 🟢 低 | 自定义 Hooks | 需要模拟 3D 环境，复杂度较高 |

### 后端 pytest 运行

```bash
# 如当前环境未安装 pytest
python -m pip install -r requirements-dev.txt

# 运行后端测试
python -m pytest -q
```

关键覆盖目标：

- route map：关键 HTTP 路径和方法必须注册完整。
- app import：`from app import app` 不启动 worker/cleanup 线程。
- LAN 门禁：门禁开/关、owner-only、远程生成条件、转发头不能提权。
- 静态文件：模型文件允许访问，敏感文件和路径穿越拒绝。
- 本地媒体图库：media/photo/video id 解析、缓存优先分页、迁移后不重建全局索引、视频扫描、poster/metadata 降级、Range 播放、相册上传文件名净化/扩展名白名单/无效图片清理。
- 视频重建：`/api/video-reconstructions`、`/api/video-reconstructions/upload`、`/api/video-reconstructions/status`、任务 kind 分发、依赖缓存、输出名唯一化、focused cleanup、sidecar 元数据、source-video 路径安全和 OOM/取消/缺依赖错误码。
- 任务队列：无需真实推理即可验证入队、列出、取消和状态变更。
- 自更新：版本/部署识别、Stable/Latest Git 精确目标、网络失败、manifest/runtime revision、dirty/active/non-main precondition、owner-only 路由、持久化阶段、自动失败恢复与响应脱敏。

### 视频 3DGS 重建 smoke checklist

视频重建稳定路线已验证平台仅写为 Windows + NVIDIA RTX 5070 Ti Laptop GPU 12GB。新增或修改相关逻辑时，至少覆盖：

- `GET /api/video-reconstructions/status` 首次可返回 checking 或缓存状态；Settings `?refresh=1` 触发后台重扫；普通首页、弹窗和任务创建不会重复同步扫描外部工具。
- 本地相册视频创建任务：只接受 video media id，拒绝照片 id、未知 id、root 外路径和源视频缺失；响应和 `/api/tasks` 不暴露 `source_video_path`。
- 拖入视频创建任务：单视频可入队，默认输出名为源视频同名 stem；多个视频或混合图片/视频时前端给出明确提示。
- 成功任务生成 `outputs/<id>.ply`，尽量生成 `.spz`，写入 `.meta.json`，并生成或复用源视频封面缩略图。
- 原视频预览入口通过 `/api/gallery/<id>/source-video` 打开，支持 Range/下载名，且不泄露绝对路径；删除本地相册来源模型不得删除原视频。
- `auto` / `object` 模式 focused cleanup 能移除外围游离 splat；清理过度时回退原始导出并记录原因；`environment` 模式不裁剪完整场景。
- Viewer 打开视频重建模型时初始画面朝向主体，左右拖拽为正常 yaw；旧 ml-sharp 单图模型预览手感不回归。
- 失败路径至少覆盖缺依赖、非法选项、输出名冲突、CUDA OOM 文本、SPZ 失败和取消清理。
- 后端默认日志只显示关键阶段和失败摘要；`SHARP_LOG_LEVEL=DEBUG` 或 verbose 模式下再输出完整外部工具日志。

### 本地媒体图库 smoke checklist

本地媒体图库属于大功能，当前若暂不引入测试框架，至少应手动或脚本化验证：

- `GET/POST/DELETE /api/photo-albums`、`POST /scan`、`GET /photos?type=all|photo|video`、`GET /photo-thumbnail`、`GET /photo-original`、`GET /video-poster`、`GET /video-original`、`GET /video-play/<id>/<token>/<filename>`、`POST /api/photo-downloads`、`POST /api/photo-conversions` 的成功与错误路径。
- 应用启动不应因为配置大量相册而等待媒体扫描；进入模型页不应触发本地媒体目录 `os.walk`。
- 相册列表应只读 catalog 摘要；旧 `index.json` 迁移归档后，多次请求列表或扫描新相册不得回退读取所有 `albums/*.json` 来重建全局索引。
- 已建立索引的相册，翻页、排序和 `type=all|photo|video` 筛选必须走每相册索引，测试可用 monkeypatch 断言不调用 `os.walk`。
- 列表返回 `thumb_url`，预览/下载使用 `full_url` 或 `preview_url` 原图地址，不能把缩略图放大当原图。
- 视频列表返回 `poster_url`、`playback_url`、`download_url` 和可选元数据；列表滚动不能加载完整视频文件。
- 中文、空格、大小写混合文件名可以生成缩略图、打开原图、下载和加入 3D 队列。
- 中文、空格、大小写混合视频文件名可以生成 poster、预览、Range seek 和下载；后端日志不能出现 latin-1 header 编码错误。
- 构造非法 media id、相对路径逃逸和 root 外路径访问会被拒绝。
- 视频播放 token 成功、过期、撤销会话失效都要覆盖；play token 不能绕过 `/api/video-original/<id>?download=1` 的 Unlocked 下载权限。
- 删除相册只移除配置、索引、该相册对应照片缩略图和视频 poster，不删除原始相册文件。
- 批量下载照片/视频 ZIP 正常包含选中媒体；取消下载或服务重启留下的 `photo-gallery-*.zip` 应在后续批量下载前按过期规则清理。
- 至少一个 1000+ 图片目录验证分页、缩略图缓存和瀑布流滚动性能。
- 移动端媒体图库真实设备验证：浮动/粘性控制区的展开、折叠、吸附或自动隐藏不应推动列表/瀑布流抖动；玻璃态控件不能退化成实心板；弱提示文案仍需可读。
- Windows、Linux、macOS 或挂载/NAS 路径至少做路径配置与不可用目录错误状态验证。
- 移动端至少验证 Chrome、一个国产浏览器和一个会接管播放器的浏览器：Chrome 应使用网页播放器；接管播放器能播放则接受；接管失败时必须展示美观失败态并保留下载。排查时确认真实视频请求是否命中 `/api/video-play/.../<filename>`，而不是只请求页面根地址。

### 局域网门禁 smoke checklist

门禁涉及隐私边界，若暂不引入测试框架，至少应手动或脚本化验证：

- 缺省 `access_control.enabled=false` 时，局域网读取模型/照片/`/files/*` 恢复旧开放行为，但设置、删除、目录管理、重启、取消任务等 owner-only API 仍拒绝远程请求。
- 门禁开启且未登录时，远程访问模型列表、媒体相册、缩略图、poster、原图、视频原文件下载、导出和 `/files/*` 返回 401，不泄露元数据或文件内容；有效视频播放 token 只允许对应视频 inline 播放。
- 访问码登录成功后，远程设备可浏览、预览、下载和导出；修改访问码或撤销会话后，旧 Cookie 和旧视频播放 token 都失效。
- 远程生成默认拒绝；只有 `access_control.enabled=true` 且 `allow_remote_generation=true` 时，已解锁远程设备才可提交 `/api/generate` 与 `/api/photo-conversions`。
- localhost owner 免访问码进入应用和设置；owner 判断不得信任 `X-Forwarded-For`、`Forwarded`、`X-Real-IP` 等客户端可控头。
- 本机 owner 在门禁关闭或未设置访问码时应默认看到启动提醒；“稍后”只关闭本次提示，“不再提示”才持久抑制。
- 敏感文件不可下载：门禁开/关两种状态下，`/files/config.json`、`/files/key.pem`、`/files/cert.pem`、`/files/app.py` 以及相对穿越/绝对路径/符号链接逃逸（如 `/files/../config.json`）都应返回 404，不泄露内容；模型下载、缩略图、原图、导出 HTML、照片缩略图/原图/打包下载仍正常。
- 仅本机绑定生效：`access_control.lan_bind_enabled=false` 重启后，服务仅监听 `127.0.0.1`，局域网 IP 连接被拒；`true` 时局域网可连。设置页切换该开关应提示需重启并触发重启。
- 调试关闭：默认（未设 `SHARP_DEBUG`）触发后端异常时响应不含堆栈，Werkzeug 交互式调试器端点不可达。
- 反向代理须知：在本机前置反向代理时，所有请求会被判为 owner；需要强制访问码时应能通过关闭 `allow_localhost_bypass`（需先设访问码）实现。
- HTTP 模式下访问码登录页应显示明文传输安全提示，HTTPS 模式下不显示。

### 便携包自更新 smoke matrix

自更新会改动可执行源码并重启服务，不能只做单元测试。完整便携包发布至少按 `cu128-rtx50`、`cu126-mainstream`、`cu128-rtx50-video-recon` 三个 target 记录结果；可对未受影响 target 使用等价自动化证据，但 bootstrap 版必须完成三包 clean-extract 验证：

- 先运行 `build_portable_release.bat -Version <version> -PlanOnly`，确认每个未跳过 target 都打印 exact Sharp GUI source SHA、`portableRuntimeRevision`、MinGit `v2.55.0.windows.3`、标准 x64 asset 和固定 SHA256；完成构建后执行 `7z t` 并核对 ZIP/`.sha256.txt`。
- 在全新目录解压，隐藏系统 Git/Python（测试 PATH 不包含二者），断言 `update.bat` 使用包内 Python 与 `.sharp-gui-tools/git/cmd/git.exe`；Git 版本、asset digest、`portable-package.json` provenance、根 `THIRD_PARTY_NOTICES.md`、包内 `LICENSE.txt` 与两棵 license tree 都存在且匹配。
- 初始受管 worktree 必须 clean 且 HEAD 等于 package metadata。用临时本地 bare remote 构造兼容目标，至少同时包含 tracked addition/modification/deletion/rename；应用后 tracked tree 必须逐项收敛到 exact target，不能留下已删除旧文件。
- 分别验证 Stable、Latest、already-current no-op 和 Latest → Stable 显式降级；版本标签必须能区分正式 `vX.Y.Z` 与 `vX.Y.Z + N commits (abcdefg)`，apply 只能使用刚检查过的 exact SHA。
- 在 Python/PyTorch/CUDA、`.video-reconstruction-env/`、模型/缓存、三个 workspace 的 inputs/outputs/model-assets/index、`config.json`、证书、日志、`portable-package.json`、`.sharp-gui-update/` 和 `.sharp-gui-tools/` 放置可校验 marker；兼容 update 与自动失败恢复后均须保留，必要时比较 hash/字节内容。
- 构造不同 `portableRuntimeRevision`、缺失/非法 manifest、缺失 `frontend/dist` 的目标，断言 checkout 前拒绝、HEAD/markers 不变且状态明确要求完整包。
- 构造 dirty tracked file、pending/running/processing generation task、非 `main` source branch、并发锁和过期 target；均须稳定拒绝且不得 fetch apply target、改文件或停止服务。远程会话及伪造 `X-Forwarded-For`/`Forwarded`/`X-Real-IP` 不能调用 check/apply。
- 注入网络/TLS/rate-limit、只读目录/磁盘不足、checkout/compile/import/frontend/health-check 失败和 updater 中断。验证错误不被误报为 up-to-date/success，mutation 后失败自动恢复 previous SHA，非终态下次启动可对账恢复且服务最终可用。
- 启动 Settings，验证当前版本、Stable/Latest、兼容/需全包原因、确认、阶段进度、预期断线重连、成功 reload 和自动失败恢复提示；同时覆盖窄屏、键盘焦点、light/dark 与 reduced-motion。
- 每个包至少完成 `portable-run.bat --verbose` 启动、更新后的 API/前端健康检查和一次自动失败恢复后启动。视频重建包还要沿用独立环境可迁移性 gate，并验证 `ns-train splatfacto --help`；核心包不得被误判为已包含视频重建环境。

---

## 推荐框架

### 前端

| 工具 | 用途 |
|------|------|
| **Vitest** | 测试运行器（与 Vite 生态一致） |
| **@testing-library/react** | React 组件测试 |
| **@testing-library/jest-dom** | DOM 断言增强 |
| **happy-dom** 或 **jsdom** | DOM 环境模拟 |

安装命令（若需添加）：
```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom happy-dom
```

### 后端

| 工具 | 用途 |
|------|------|
| **pytest** | 测试运行器 |
| **pytest-flask** | Flask 应用测试辅助（当前未强制依赖，Flask 原生 test client 已够用） |

---

## 文件命名约定

| 平台 | 命名模式 | 位置 |
|------|----------|------|
| 前端组件测试 | `ComponentName.test.tsx` | 组件目录内 |
| 前端工具函数 | `format.test.ts` | `utils/` 目录内（与源文件同级） |
| 前端 Hook | `useViewer.test.ts` | `hooks/` 目录内 |
| 后端 API | `test_api.py` | 项目根目录 `tests/` |
| 后端工具 | `test_ply_to_splat.py` | 项目根目录 `tests/` |

### 文件结构示例

```
frontend/src/
├── utils/
│   ├── format.ts
│   └── format.test.ts          # 工具函数测试
├── components/common/Button/
│   ├── Button.tsx
│   ├── Button.module.css
│   ├── Button.test.tsx          # 组件测试
│   └── index.ts

tests/                            # 后端测试（项目根目录）
├── test_api.py
├── test_ply_to_splat.py
└── conftest.py                   # pytest fixtures
```

---

## 测试编写指南

### 前端工具函数测试示例

```typescript
// utils/format.test.ts
import { describe, it, expect } from 'vitest';
import { formatFileSize, debounce } from './format';

describe('formatFileSize', () => {
  it('formats bytes correctly', () => {
    expect(formatFileSize(0)).toBe('0 B');
    expect(formatFileSize(1024)).toBe('1.0 KB');
    expect(formatFileSize(1048576)).toBe('1.0 MB');
  });
});
```

### 前端组件测试示例

```typescript
// Button/Button.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('calls onClick handler', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click</Button>);
    fireEvent.click(screen.getByText('Click'));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
```

### 后端 API 测试示例

```python
# tests/test_api.py
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_gallery_returns_json(client):
    """图库 API 应返回 JSON 列表"""
    response = client.get('/api/gallery')
    assert response.status_code == 200
    data = response.get_json()
    assert 'items' in data
```

### 模型资产库 smoke checklist

模型资产库属于本次 `add-model-asset-library` 的主路径，修改相关逻辑时至少覆盖：

- route map 必须显式断言模型资产列表、详情、导入、资料 `POST/PATCH`、封面上传/刷新、下载和删除的路径与方法；不能只靠其它 API 合约测试间接证明注册成功。
- `GET /api/model-assets` 覆盖稳定游标、筛选、排序、格式计数、空结果、无更多结果和分页期间新增/删除；暖索引后的下一页、筛选和排序可用 monkeypatch 断言不调用全量 `os.listdir` / `os.walk`、不逐文件 `stat` 完整 `outputs/`。
- `GET /api/model-assets/<asset_id>` 覆盖详情字段、默认格式回退、源媒体缩略图/视频 poster 和未知元数据降级。源文件消失时必须得到 `available=false`、`files=[]`、`formats=[]`、`default_open_url=null`、`download_url=null`，并且整个列表不能因单资产竞态 500。
- 导入覆盖 `.ply/.spz/.splat/.rad` 白名单、64 文件、2 GiB 单文件、10 GiB 整批和请求体上限；验证 Unicode/空格/大小写原始名称与下载名保留，而物理存储名安全唯一，客户端路径片段和非法后缀不能影响目标路径。
- 批量导入同时覆盖全成功、部分成功和全部失败：逐项 `failed[].code` / filename 在 2xx 与非 2xx 中都保留并可本地化；索引写入或磁盘提交故障时回滚本批孤儿文件，不得只返回通用 HTTP 状态。
- 使用线程屏障覆盖两个同名文件并发导入，断言得到不同物理文件且删除一个不影响另一个；并覆盖资料更新/删除、封面上传/删除、封面刷新/上传交错，删除后的旧请求不得复活索引记录或孤立文件。
- 索引测试区分 missing、valid、损坏 JSON 和 schema 非法：只有 missing 可初始化；损坏索引后的任意编辑、导入、封面或删除不得覆盖原文件，需验证隔离/诊断/恢复行为、已有导入文件仍保留，并且本次未提交的新导入文件被回滚。
- 封面覆盖 10 MiB 上限、实际格式/扩展名、像素维度、无效图片和路径约束；无效替换必须保留旧封面，JPG/PNG/WebP 跨扩展替换/刷新不得遗留或复活旧封面。
- 删除覆盖磁盘拒绝、索引写入失败与文件已消失；只有文件和索引达到约定一致状态才返回成功。删除导入资产不能误删 `outputs/`、相册原图或视频来源文件。
- `/files/*` 和模型资产 list/detail/download/delete 都要测试根内文件 symlink、受控根自身 symlink/junction/Windows reparse point、路径穿越和跨盘符；必须拒绝 workspace 外目标以及 `.model-asset-library/index.json`、`config.json`、证书和源码。
- 权限同时验证 API 与 UI：读取为 Unlocked；导入/编辑/封面为 Owner/Conditional；删除仅 Owner。远程只读用户看不到或不能触发注定 403 的写按钮，权限原因使用本地化应用内反馈而非原生 alert。
- 前端列表用可控 Promise 模拟筛选/排序/游标响应乱序，断言旧 generation 不能覆盖当前 query、列表、游标、loading 或 error；密度变化只改 CSS 列数并保持数据与滚动位置。
- 模型来源回归覆盖 `gallery`、`model-asset-generated`、`model-asset-imported`、`temporary`：任务/旧图库刷新不关闭非 gallery 模型，入口传递真实格式和文件大小；设置变更后的 viewer 重载保留来源。
- 拖拽烟测覆盖主模型页单文件临时预览、多文件批量导入、资产库内单/多文件直接导入、混合/不支持文件反馈；替换、关闭、卸载和导入成功后 Object URL 均被 revoke。
- 封面队列只处理已加载且可见/新导入资产，限制总体并发；共享 WebGL renderer 时渲染区间必须串行，使用两个不同模型的交错 Promise 验证不会串图、错绑 asset id 或在卸载后写回。
- 生成资产可复用旧导出/分享；导入资产和临时预览不得调用旧 `/api/export/<id>`。Settings 切换 SPZ/PLY 后，资产库、近期模型、打开和下载优先使用对应格式，缺失时按可用文件回退。
- 键盘烟测分别聚焦卡片主动作、详情、下载和删除按钮并按 Enter/Space，断言只触发目标动作；触控路径不依赖 hover，明显 shimmer/加载动画在 `prefers-reduced-motion` 下停用或降级。
- 视觉与上下文烟测：桌面卡片空白区域直接打开 viewer，移动端点击卡片打开详情；顶部工具栏悬浮玻璃不切断内容；近期模型即使为空/失败也保留“查看全部”和固定存储摘要，返回资产库后筛选、选择、已加载批次和滚动位置不丢失。
- workspace 切换测试覆盖目标被占用、目标是普通文件、无写权限和锁创建失败；响应使用稳定 JSON 错误且 `config.json` 不变。预检成功不替代新进程启动时正式获取 workspace 锁。
