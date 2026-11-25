# 应用依赖与旧便携包升级 / Application dependencies and portable upgrades

代码、纯 Python 应用依赖和基础运行环境分别管理。更新器会为目标提交准备固定版本、固定 SHA256 的应用依赖，验证通过后再切换代码。Python、Torch/CUDA、原生工具、模型和工作区保留。

Application code, pure Python application dependencies and the base runtime are managed separately. The updater prepares exact, integrity-checked dependencies before switching code. Python, Torch/CUDA, native tools, models and workspaces are preserved.

## 旧包如何升级 / Upgrading an old bundle

1. 从规范仓库正式 Release 下载 `sharp-gui-update-tool.zip` 和 `.sha256.txt`，核对 SHA256。这个工具只包含小型升级程序，不含 Python/CUDA。 / Download the lightweight ZIP and checksum from the canonical formal Release and verify SHA256.
2. 正常关闭 Sharp GUI，将工具解压到已有便携包根目录，保留其 `.sharp-gui-upgrade/` 子目录。 / Close Sharp GUI normally and extract into the existing portable root, keeping the helper subdirectory.
3. 运行 `upgrade-portable.bat`。默认使用 Stable，可用 `upgrade-portable.bat --channel latest` 选择主线，或加 `--check` 只检查。 / Run the launcher; Stable is default, Latest selects main, and `--check` checks only.
4. 升级成功后继续使用原来的 `portable-run.bat`。后续可在设置中更新。 / After success, use the existing launcher; subsequent updates are available in Settings.

轻量工具随修复版正式发布提供，当前开发分支可运行 `python tools/build_update_bootstrap.py` 生成本地测试产物。尚未发布新 Release 时，不应宣称公开下载源已经包含本工具。

The tool is distributed with the repaired formal release. Developers can build a local artifact with the command above. Before that release, do not claim that the public download already includes it.

无受管 Git、基础环境不兼容、tracked 文件有本地修改或已有服务运行时，工具会明确拒绝，不强杀进程、不改写出厂元数据。未取得实际归档证据的旧版本不列入兼容范围。当前候选和实际验收结果记录在 [update-verification.json](update-verification.json)。

The tool refuses unmanaged snapshots, incompatible base environments, tracked modifications and running services. It does not kill processes or rewrite package provenance. Unsupported historical baselines remain blocked; actual package evidence is recorded separately.

## 依赖与失败恢复 / Dependencies and recovery

- 应用依赖锁位于 `app-dependencies.lock.json`，清单中的摘要为排序后紧凑 JSON 的 SHA256，避免换行格式影响校验。 / The manifest binds the canonical JSON SHA256 of the exact dependency lock.
- 经过验证的 pure-Python wheels 保存在安装目录的 `.sharp-gui-update/dependencies/sets/<lock digest>/`，通过只读加载器直接导入。每次加载检查完整集合与 wheel 摘要，不向基础 site-packages 安装。 / Verified immutable wheel sets are loaded without modifying base site-packages.
- 普通页面、状态查询和应用 import 不联网安装。源码安装器显式调用 `python tools/prepare_app_dependencies.py`；需要手工准备时也使用此命令。 / Preparation runs only through explicit installation/update commands.
- 下载失败时原服务保持可用；代码切换后验证失败会恢复原提交，对应依赖由原提交的清单选择。依赖集合暂不自动清理，避免误删历史降级或恢复引用。 / Download failures preserve the running service; post-switch failures restore the original matching combination. Sets are retained for recovery and downgrade.
- 若更新进程被强制结束，请先正常关闭应用，再运行更新命令或轻量工具。它会先恢复未完成事务；未知 HEAD 或无法恢复时明确报告，不能继续覆盖。 / After interruption, close the application and run the updater or tool to recover the persisted transaction first.

## 开发与发布约束 / Development and release checks

`portableCompatibility` 按 target 声明可接受的出厂 runtime、Python minor 和 Torch 版本。历史清单没有此字段时继续使用旧规则。包布局或压缩变化不自动切断兼容性。`portableRuntimeRevision` 保留历史标识，不降低或伪造。

Compatibility is explicit per portable target and includes the original runtime baseline, Python minor and Torch version. Historical manifests keep their original rules. Layout/compression changes do not automatically invalidate a compatible base.

`updateChangeClasses` 将受支持安装器中的应用依赖集成与基础环境变更区分开。原生安装器等未分类敏感变更仍被 CI 拦截。应用依赖变化必须维护锁、准备/恢复测试与轻量工具；协议变化必须声明 `bootstrapSupport`，并验证当前支持客户端能通过持久入口迁移。

CI separates dependency integration from base changes, rejects unclassified sensitive changes, and requires locks and transaction tests. Protocol changes require an explicit persistent bootstrap path.

发布前验证旧包到修复版、修复版到后续 A/B 版本、降级与失败恢复。实际便携包证据和合成测试分开记录。本次修复不需要重新构建完整 Windows 环境，也不自动安装 ComfyUI、外部节点或模型。

Release verification includes legacy migration, subsequent A/B updates, downgrade and recovery, distinguishing real archives from synthetic tests. This change does not rebuild Windows runtimes or install external ComfyUI components.
