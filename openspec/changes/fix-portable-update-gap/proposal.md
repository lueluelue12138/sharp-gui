## Why

当前自更新要求便携包运行环境版本与目标版本完全相同，却不负责补齐应用依赖。三个 ComfyUI 工作台新增的小依赖 `websocket-client` 因而被视为需要重新下载完整包，之前仅改变压缩与裁剪方式的版本也阻断了旧包更新。

需要在发布新版本前补齐依赖更新与旧更新器的过渡路径，让兼容的现有便携包可以持续获得应用更新，并在失败后保持可用。

## What Changes

- 将基础运行环境兼容性、便携包内容布局和应用依赖分别管理。压缩、裁剪以及可隔离的小依赖变化不再直接要求换完整包。
- 随应用更新准备、校验和切换固定版本的纯 Python 应用依赖，首个覆盖项为 `websocket-client`，用户无需手动安装进度组件。
- 将应用提交与应用依赖作为同一更新事务，覆盖下载失败、重启失败、断电恢复以及稳定版降级。
- 为已发布的旧更新器提供长期可用的小型过渡升级工具，跨过旧版的严格相等检查。不得要求用户碰巧安装某个已经被后续版本取代的中间标签。
- 在更新中心区分可直接更新、需要轻量过渡升级、基础环境不兼容以及依赖准备失败，并提供一致的中英文提示。
- 调整兼容性检查、构建与发布规范，要求发布前验证旧包到新版本以及新版本之间的连续更新。

### Scope

包含已带受管 Git 与包内 MinGit 的 Windows 便携包，以及使用同一事务的 Git 源码安装。首轮迁移候选为实际发布的 runtime 4 与本地已验证的 runtime 6 三种便携包目标，兼容支持必须以实包验证结果为准。

不自动安装 ComfyUI、外部节点、模型或显卡驱动，不原地替换 Python、PyTorch、CUDA、Brush、COLMAP 等基础运行环境，不把没有受管 Git 的历史快照直接当成可升级便携包。本轮不重新构建 Windows 完整便携包，也不在修复验收前发布新正式版。

## Capabilities

### New Capabilities

- `application-dependency-updates`: 固定版本应用依赖的准备、隔离加载、原子切换与失败恢复。
- `portable-update-bootstrap`: 已发布旧便携包通过轻量工具进入新版更新机制，工具长期可获得并保留数据与基础环境。

### Modified Capabilities

- `application-self-update`: 显式基础环境兼容、应用与依赖联合事务、更新中心状态和分类兼容性守卫。

## Impact

- `update-manifest.json` 与新增应用依赖锁定清单，保留旧清单的识别路径。
- `backend/services/self_update.py`、`backend/routes/updates.py`、`tools/update.py`、`update.bat`、`update.sh`，以及新的应用依赖与过渡升级工具。
- `app.py` 和必要的 Python 入口，在导入应用依赖前选择经过验证且与目标提交绑定的依赖集合。
- `frontend/src/components/layout/Settings/UpdateSettingsSection`、`frontend/src/api`、`frontend/src/types`、中英文资源及 `frontend/dist`。
- `tools/check_update_compatibility.py`、便携构建脚本、`.github/workflows`、更新相关测试与发布检查。
- README、中英文更新说明、`.agents/rules/self-update.md` 与提交发布规范，修正“小依赖变化必须下载完整包”的既有约束。
