---
name: commit-and-release
description: Sharp GUI 项目的 Commit Message、Release Note、Windows 完整便携包一键打包与网盘发布流程规范
---

# Commit Message & Release Note 规范

本 Skill 定义了 Sharp GUI 项目的 Git Commit Message 和 GitHub Release Note 的书写格式规范。当用户要求生成 commit message 或 release note 时，必须严格遵循以下规则。

---

## Commit Message 规范

### 作者归属（提交前检查）

- Agent / AI 执行提交时，`Author` 使用实际工具身份；不得把不同工具统一写成固定 Agent，也不得把推送账号直接当作作者。优先使用工具官方身份；没有官方邮箱时可使用清晰工具名和中性未绑定邮箱。
- 将实际参与需求、讨论、优化、验证或验收的人类参与者写入 `Co-authored-by:`。姓名和邮箱取当前参与者已确认的 GitHub 关联身份，优先使用 GitHub noreply 邮箱；**不得在仓库规则中写死某位维护者的信息**。本人手动提交时无需重复添加自己。
- 每次提交前检查 `git config --show-origin --get user.name`、`git config --show-origin --get user.email` 和 `git var GIT_AUTHOR_IDENT`。本地配置只能在确认属于当前人类参与者后用于共同作者；无法确认时先询问，不得猜测。
- Agent 身份只对本次命令临时覆盖，例如 `git -c user.name="<Agent>" -c user.email="<Agent email>" commit ...`；除非用户明确要求，不修改全局 Git 身份。
- 提交正文与 footer 之间留一个空行；每位参与者只保留一条：

  ```text
  Co-authored-by: <参与者姓名> <GitHub 已关联邮箱>
  ```

- 推送前执行 `git show -s --format=fuller HEAD`，确认实际 Agent 作者和共同作者归属正确。错误只能在未推送时修正；不得擅自改写已推送历史。

### 格式

使用 **Conventional Commits** 格式，语言为 **中文**。

> 生成 commit message 前，先执行 `git diff --staged --stat`（必要时再看 `git diff --staged`）核对真实改动范围，确保 type / scope 与描述和实际改动一致，避免"描述与改动不符"。

#### 标题行

```
type(scope): 简要描述
```

- **type**: `feat` | `fix` | `refactor` | `chore` | `docs` | `style` | `perf` | `revert`
  - `feat` 新功能、`fix` 修复、`refactor` 重构、`perf` 性能、`style` 纯样式/格式、`docs` 文档、`chore` 杂项/构建/依赖、`revert` 回滚
  - **例外**：merge 提交、`Initial commit`、自动生成的提交不强制套用本格式
- **scope** (可选): 影响的模块，建议从以下约定值中选取，确需新增时保持一致：
  - 功能域：`photo` | `video` | `viewer` | `frontend` | `app` | `backend` | `share` | `vr`
  - 工程域：`install` | `update` | `run` | `release` | `build` | `openspec`
  - 文档可用复合形式：`docs(openspec)` | `docs(frontend)` | `docs(video)`
- 标题行 **不超过 72 字符**，只写"做了什么"；**细节一律进正文**，不要用 ` - ` 把多条变更塞进标题
- 不以句号结尾

#### 原子提交 (优先)

- **优先一个提交只做一件事**：type 单一、范围聚焦，方便 review 与回滚
- 确有多项改动必须合并时：标题取**主导改动**对应的 type，其余变更在正文按分类说明（见下方"大改动"示例）；**不要在标题用 `&` 堆叠多个 type**

#### 破坏性变更 / 关联 Issue

- 破坏性变更：在 type 后加 `!`（如 `feat(app)!: ...`），并在正文末尾追加一行 `BREAKING CHANGE: 说明`
- 关联 issue / PR：在正文末尾追加 `Closes #123` 或 `Refs #123`

#### 前端构建产物 (涉及前端改动时必须)

- **只要改动涉及 `frontend/`**，提交前必须先执行 `npm run build` 重新生成 `dist/`，并将更新后的 `dist/` 一并纳入提交，确保发布版本无需用户自行构建即可使用最新前端
- 纯后端 / 文档 / 脚本改动**无需**重建 `dist/`，避免产生无意义的大 diff
- ⚠️ **自更新使这条从"体验问题"变成"正确性问题"**：进入 `main` 的每个提交都可能被便携用户当作 Latest 目标安装，而更新会校验目标提交里的 `frontend/dist/index.html`。带前端源码改动却漏提交 `dist/` 的提交，会让便携用户检查到一个**不兼容目标**（而不是"自己构建一下"），也会让 dist 与源码不一致的版本被装到用户机器上
- 因此 `chore(build): 同步前端构建产物` 只用于**补救已漏提交产物**的场景，不能作为常规拆分方式把 dist 推到后续提交

#### 版本号变更

- 版本号以 `version.txt` 为准；发布时使用**独立提交** `chore(release): 发布 vX.Y.Z`（同步 `version.txt`），便于检索版本节点
- **不要**把版本号 bump 混进功能提交里
- `version.txt` 必须与即将打的 tag **完全一致**：`release.yml`、`release.sh`、`release.bat` 都会比对，不一致直接失败。原因是自更新按 exact commit 安装，Release 包的版本标识不能再由 CI 事后写入
- `release.sh` / `release.bat` 还要求 Git 工作区**完全干净（含未跟踪文件）**，因为发布包必须是某个提交的精确快照。先提交，再打包，不要在 dirty 树上出包

#### 自更新带来的提交约束（容易漏，必须逐条检查）

自更新让 `main` 上的**每个提交**都可能被便携用户直接安装。以下四条不是风格建议，漏掉会直接影响已发布的用户。

**1. 运行时敏感改动必须在同一个提交递增 `portableRuntimeRevision`**

触发路径（`tools/check_update_compatibility.py` 的判定口径）：

- `requirements*.txt`（`requirements-dev.txt` 除外）、`pyproject.toml`、各类依赖锁文件
- `install.bat` / `install.sh` / `build_portable_release.bat`
- `tools/install_torch.py` / `tools/install_video_reconstruction.py`
- `tools/build_portable_package.ps1` / `tools/build_portable_release.ps1` / `tools/portable_update_common.ps1`

改了这些就说明"新代码需要新的运行环境"，必须同提交把 `update-manifest.json` 的 `portableRuntimeRevision` 加一，**并配套发布新的完整便携包**。CI 的 `update-compatibility.yml` 会拦住只改脚本不提版本的 PR。反过来也不许为了过 CI 随便递增而不发对应运行时。

普通前后端源码、路由、组件、目录重构和 `frontend/dist` 变化**不需要**递增。

**2. 绝不能把用户数据或运行时路径纳入版本管理**

一旦某个提交跟踪了这些路径，**所有便携包用户的更新都会被拒绝**（提示"会覆盖受保护的便携运行时文件"），且提示信息与真实原因看不出关联，非常难查：

`config.json`、`*.pem`、`*.log`、`workspace/`、`models/`、`inputs*/`、`outputs*/`、`model-assets*/`、`python/`、`venv/`、`ml-sharp/`、`.video-reconstruction-env/`、`.sharp-gui-tools/`、`.sharp-gui-update/`、`portable-package.json`、`portable-run*.bat` 等。

完整判定口径以 `backend/services/self_update.py` 的 `PROTECTED_RUNTIME_PATHS` 与 `target_tracks_protected_runtime()` 为准，不要凭这里的摘要下结论。提交前不要用 `git add --force` 绕过 `.gitignore`；不确定时执行 `git status --porcelain --untracked-files=all` 复核暂存内容。

**3. 新增或修改更新错误码时，前后端与双语文案必须同批提交**

后端新增一个 `update_*` 错误码，就要同步 `UpdateSettingsSection.tsx` 的 `CODE_KEYS` 映射和 `en.json` / `zh.json` 文案，否则用户看到的是"更新服务返回了无法识别的状态"。同理，删除后端不再产生的码时，映射和文案一并清掉，别留孤儿。

**4. scope 选择**

- 自更新后端 / 前端 / CLI / manifest / CI 守卫 → `update`
- 便携包构建与 MinGit 打包 → `build`
- 发布流程、版本号、Release 工作流 → `release`

> 改动自更新相关代码时，提交前按 [.agents/rules/self-update.md](../../rules/self-update.md) 第 10 节「验证清单」执行测试与检查；Windows 便携包相关改动另见 [.agents/rules/testing.md](../../rules/testing.md) 的「便携包自更新 smoke matrix」。

#### 正文 (大改动才需要)

- 用空行与标题分隔
- 按分类组织，分类名后接冒号
- 用 `-` 列表描述具体变更
- 二级细节用缩进 `  -`
- 简洁，不写废话
- 语言统一 **中文**；历史遗留的英文提交**不强制回改**

### 示例

**小改动** (单行即可):

```
fix: 赋予 update.sh 执行权限
```

**中等改动** (附简短说明):

```
fix: update.py 解压路径修复 - 移至 tools/ 后解压到了错误目录

get_script_dir() 返回 tools/ 而非项目根目录，导致 zip 被解压
到 tools/ 内而不是项目根目录。改为返回 tools/ 的父目录。
```

**大改动** (分类组织):

```
feat: 添加自动更新脚本 & 重构工具目录 & 修复 install.bat 闪退

新增功能:
- 添加 update.py/update.bat/update.sh 自动更新脚本
  - GitHub Release 版本检测 (无 API 限流)
  - 版本比较防止降级 (pre-release → 旧 stable)
- release.yml 自动写入 version.txt

目录重构:
- 工具脚本移至 tools/ 目录
  - detect_cuda.py, download_model.py, generate_cert.py, update.py
- 更新所有引用: install.bat/sh, release.yml, README.md 等

Bug 修复 (install.bat):
- 修复 CUDA 检测闪退: for /f 内联 Python 语法冲突
- 修复 nvcc 版本解析带尾部逗号 (12.4, → 12.4)
```

---

## Release Note 规范

### 定位

- **面向普通用户**，不展示过多技术实现细节
- **中英双语**，每行先中文后英文，用 `/` 分隔
- 语气简洁明了，突出用户能感知到的变化和价值
- 输出时使用 markdown 代码块包裹，方便用户直接复制

### 结构模板

```markdown
## 🚀 vX.Y.Z(-rc.N) (Pre-Release)

> ⚠️ 这是预发布版本，用于测试验证。正式版将在测试通过后发布。
>
> ⚠️ This is a pre-release for testing. Stable release coming after validation.

---

### 🎯 功能标题 / Feature Title

- **中文粗体关键词**: 中文描述 / English description
- **中文粗体关键词**: 中文描述 / English description

### 🐛 Bug 修复 / Bug Fixes

- **修复 xxx**: 中文描述 / English description

### 🔧 技术改进 / Technical Improvements

- 中文描述 / English description

---

### 📦 快速使用 / Quick Start

1. 下载 `sharp-gui-vX.Y.Z.zip` / Download the zip file
2. 解压后运行安装脚本 / Extract and run install script:
   - **Linux/macOS**: `./install.sh && ./run.sh`
   - **Windows**: `install.bat` 然后 `run.bat`
3. 浏览器访问 / Open browser: `https://127.0.0.1:5050`

### 🔄 从旧版本更新 / Update from Previous Version

- **便携包用户（bootstrap 版及更新）**: 打开 设置 → 更新中心，选择稳定版后安装；工作区、模型和运行环境都会保留 / Settings → Update Center, choose Stable and install; workspace, models and runtime are preserved
- **便携包用户（bootstrap 之前的旧包）**: 需要最后一次手动下载完整包，之后即可在界面内更新 / One final manual full-package download, then in-app updates work
- **Git 源码用户**: `git pull origin main` 后重跑 `install.bat` / `./install.sh`，或用 `update.bat --channel stable` / Pull and re-run install, or use the update CLI
- **通用 Release zip 用户**: 该快照没有受管更新基线，只能查看版本状态；请改用 Git 克隆或完整便携包 / Generic zip snapshots are status-only; switch to a Git clone or a full portable package

📖 **中文详细教程**: [查看 README](https://github.com/lueluelue12138/sharp-gui)

📖 **English Guide**: [View README.en.md](https://github.com/lueluelue12138/sharp-gui/blob/main/README.en.md)
```

### Windows 完整便携包发布步骤

当用户要求发布 Windows 完整包、网盘包、一键打包、便携包、RTX 50 / CUDA 包时，优先使用项目根目录的一键入口：

```bat
build_portable_release.bat
```

默认行为：

- 默认从 `version.txt` 或 Git tag 自动提取版本号，生成包含真实版本号的包名。
- 若解析结果不像 `vX.Y.Z`，脚本默认会拒绝继续，避免误生成 `local-*` 测试包；测试时才使用 `-AllowLocalVersion`。
- 构建 React 前端。
- 前端构建会优先复用现有 `frontend\node_modules`，通过 Node 直接调用 TypeScript 与 Vite 入口；只有缺失或构建失败时才安装依赖，避免 npm 版本差异导致 lockfile 被改、`npm ci` 失败或 Windows `.bin` shim 权限问题。
- 使用主 `venv` 生成 `cu128-rtx50` 完整包。
- 使用主 `venv` 和 `.video-reconstruction-env` 生成 `cu128-rtx50-video-recon` 视频重建完整包。
- 自动准备 `.portable-venvs\cu126` 并生成 `cu126-mainstream` 完整包。
- 生成 `.sha256.txt`。
- 用 7-Zip 测试 ZIP 完整性。
- 生成 `portable-dist\portable-release-template-<version>.md`，用于复制到 GitHub Release 正文并填写网盘链接。
- 默认保留 `.portable-venvs` 作为下次打包加速缓存，并保留 `portable-dist` 中的历史旧版本产物；脚本结束时会打印缓存位置和手动清理命令。

常用命令：

```bat
build_portable_release.bat -Version v1.2.3
build_portable_release.bat -PlanOnly
build_portable_release.bat -Version v1.2.3 -PlanOnly
build_portable_release.bat -AllowLocalVersion -PlanOnly
build_portable_release.bat -SkipCu126
build_portable_release.bat -SkipCu128
build_portable_release.bat -SkipVideoRecon
build_portable_release.bat -CleanBuildVenvs
build_portable_release.bat -CleanOldArtifacts
```

清理策略：

- 默认保留最终产物：`portable-dist\sharp-gui-*.zip`、对应 `.sha256.txt`、`portable-release-template-*.md`。
- 默认保留 `.portable-venvs` 作为 `cu126` 打包加速缓存，避免每次重新下载和安装 PyTorch。
- 默认清理 `.portable-build` 临时 staging 目录，避免异常之外的中间目录残留。
- 默认保留旧版本 ZIP，避免误删历史发布包。
- 如需清理 `cu126` 打包缓存，可显式加 `-CleanBuildVenvs`，或手动删除 `.portable-venvs`。
- 如需清理旧版本便携包产物，可显式加 `-CleanOldArtifacts`，或手动删除 `portable-dist` 中不需要的版本。

根目录只保留 `build_portable_release.bat` 作为公开入口；`tools/build_portable_package.ps1` 是内部单包构建实现，除非用户明确要求调试单个目标包，否则不要让用户直接调用它。

发布检查清单：

- 确认 `portable-dist\*.zip` 与对应 `.sha256.txt` 已生成，且文件名包含真实版本号 `vX.Y.Z`，不能发布 `local-*` 或 `v-local-test` 包。
- 确认 `portable-dist\portable-release-template-<version>.md` 已生成，并将网盘链接补进去。
- `cu128-rtx50` 面向 RTX 50 系列核心包；`cu128-rtx50-video-recon` 面向 RTX 50 / CUDA 12.8 视频重建完整包；`cu126-mainstream` 面向 RTX 50 以下主流 NVIDIA 核心包。
- 首版完整便携包不提供纯 CPU 包。
- 不要把完整大 ZIP 上传到 GitHub Release 资产；GitHub Release 只贴网盘链接和 SHA256。
- 生成 commit message 或 release note 时，必须提到 Windows 完整便携包的适用显卡和校验方式。

### Release Note 中的自更新表述纪律

- **bootstrap 版**（首个内置 MinGit 与受管 worktree 的完整便携包）必须在 release note 里明确写出："这是最后一次需要手动下载完整包，之后可在界面内更新。"
- **不得承诺旧便携包能原地获得新更新能力**。bootstrap 之前的包没有内置 Git 和受管基线，只能再下载一次完整包。
- 若本次 `portableRuntimeRevision` 有变化，release note 必须写明**必须下载新完整包、不能用代码更新**，并说明原因（Python / CUDA / 视频重建环境等大型运行环境变了）。
- 描述 Latest 通道时要点明它包含正式发布之后的提交、测试较少；描述 Stable 时点明它只取正式 `vX.Y.Z` 版本。
- 可以写"更新失败会自动恢复到更新前的版本"，**不要**写成用户可以手动回滚。
- 提到保留范围时按用户语言写：工作区、模型、配置、证书和运行环境都会保留，只替换应用代码。

### 规则

0. 提交代码之前，确保执行前端构建脚本 `npm run build`，生成最新的 `dist/` 目录内容，并将其包含在 commit 中。这样可以确保发布版本包含最新的前端代码，让用户无需自行构建即可使用最新功能。
1. Pre-release 版本标题带 `Pre-Release`，正式版不带
2. Pre-release 需要顶部 `> ⚠️` 警告 blockquote，正式版不需要
3. 章节标题使用 emoji: 🆕🎮📥🐛🔧📁🔄 等，按内容选择合适的
4. 每个 bullet 格式: `- **粗体关键词**: 描述 / English desc`
5. 如有从旧版升级的说明，加 `### 🔄 从旧版本更新 / Update` 章节
6. 底部固定 Quick Start + README 链接
7. 不要写代码实现细节（如函数名、变量名），只写用户能感知的变化
8. 输出必须用 markdown 代码块包裹 (`markdown ... `)，方便用户复制
9. 更新命令只有 `--channel stable|latest`、`--check`、`--yes` 三个参数。**`--pre` 和 `--rollback` 已废除**，不要在 release note 里出现
   - Stable 通道只解析正式 `vX.Y.Z` tag，**预发布版本无法通过 Stable 获得**
   - 预发布测试者若该提交已进入 `main`，用 `--channel latest`；否则手动下载对应 Release / 完整便携包
   - 不要把"回滚"写成用户可操作功能：只有目标验证失败时的**自动**恢复，没有成功后的手动回滚入口
10. 生成release note 前，先完整获取并整理上一个tag到目前main分支的所有commit message，确保release note的准确性和完整性
11. 生成正式版 release note前，完整获取并整理github上，上一个正式版本到目前最新的pre-release版本的release note，确保正式release note的准确性和完整性
