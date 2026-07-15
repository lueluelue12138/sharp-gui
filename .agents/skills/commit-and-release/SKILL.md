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
- 若仅同步构建产物，可单独用 `chore(build): 同步前端构建产物` 提交，避免淹没功能 diff

#### 版本号变更

- 版本号以 `version.txt` 为准；发布时使用**独立提交** `chore(release): 发布 vX.Y.Z`（同步 `version.txt`），便于检索版本节点
- **不要**把版本号 bump 混进功能提交里

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

- **Release 包用户**: 运行 `update.bat` 或 `./update.sh` / Run update script
- **Git 用户**: `git pull origin main` 后重跑 `install.bat` 或 `./install.sh` / Pull and re-run install

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
9. Pre-release 版本的更新指引中，`update.bat`/`update.sh` 必须加 `--pre` 参数（如 `update.bat --pre` 或 `./update.sh --pre`），正式版不需要
10. 生成release note 前，先完整获取并整理上一个tag到目前main分支的所有commit message，确保release note的准确性和完整性
11. 生成正式版 release note前，完整获取并整理github上，上一个正式版本到目前最新的pre-release版本的release note，确保正式release note的准确性和完整性
