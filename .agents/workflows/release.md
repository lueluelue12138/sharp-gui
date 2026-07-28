# 工作流：版本发布

## 发布方式

项目通过 **Git tag 触发 GitHub Actions** 自动构建并发布到 GitHub Releases。

> 📝 **Commit Message 和 Release Note 格式**请参考 Skill：[.agents/skills/commit-and-release/SKILL.md](../skills/commit-and-release/SKILL.md)，其中定义了 Conventional Commits 中文规范和中英双语 Release Note 模板。

---

## 完整流程

### 1. 确认代码就绪

```bash
# 确保在 main 分支，代码已提交
git status
git log --oneline -5
```

同时确认 `update-manifest.json` 存在且反映本次源码/便携运行时兼容边界；任何可成为 Latest 的 `main` 提交都必须是可检查的完整更新目标。

### 2. 构建前端

```bash
./build.sh
# 等效于:
# cd frontend && npm install && npm run build
```

验证 `frontend/dist/` 目录已生成且与当前源码一致。便携用户没有 Node/npm，缺少或陈旧的已构建前端必须阻止代码更新目标发布。

### 3. 本地测试

```bash
./run.sh
# 访问 https://127.0.0.1:5050 确认功能正常
```

### 4. 创建 Git tag 并推送

先确认 `version.txt` 已通过独立的 `chore(release): 发布 vX.Y.Z` 提交同步到目标版本号：tag 与 `version.txt` 不一致时，`release.yml`、`release.sh`、`release.bat` 都会直接失败。自更新按 exact commit 安装，Release 包的版本标识不能再由 CI 事后写入。

```bash
# 正式版
git tag v1.2.0
git push origin v1.2.0

# 预发布版（tag 中包含 `-`）
git tag v1.3.0-beta.1
git push origin v1.3.0-beta.1
```

### 5. GitHub Actions 自动执行

推送 tag 后，`.github/workflows/release.yml` 自动触发：

1. **Checkout 代码**
2. **Setup Node.js 20**
3. **构建前端**：删除平台相关 lockfile 后执行 `npm install` + `npm run build`
4. **创建发布包**：
   - 复制 `app.py`、脚本文件、`tools/`、`templates/`、`static/`、`frontend/`
   - 删除 `node_modules/`、`.vite/`、`src/`（仅保留 `dist/`）
   - 校验 `version.txt` 与 tag 一致（不一致直接失败），并随包复制 `version.txt`、`update-manifest.json`、`THIRD_PARTY_NOTICES.md`
   - 还原构建过程改动的 `package-lock.json` 与 `dist`，保证归档字节与 tag 提交一致
   - 打包为 `sharp-gui-vX.Y.Z.zip`
5. **创建 GitHub Release**：
   - tag 含 `-` → 自动标记为 Pre-release
   - 自动生成 Release Notes

### 6. 验证

- 检查 [GitHub Releases 页面](https://github.com/lueluelue12138/sharp-gui/releases)
- 确认 zip 文件已上传
- 确认 Pre-release 标记正确
- 确认正式 Release 的 tag/commit 与 Stable 检查结果一致；draft 或 prerelease 不能成为 Stable

---

## 本地打包（不通过 CI）

```bash
./release.sh v1.2.0
# 输出: sharp-gui-v1.2.0.zip
```

`release.sh` 执行相同的构建和打包流程，但在本地完成。

---

## 版本号规范

| 格式 | 类型 | 示例 |
|------|------|------|
| `vX.Y.Z` | 正式版 | `v1.0.0`, `v1.2.3` |
| `vX.Y.Z-beta.N` | Beta 预发布 | `v1.3.0-beta.1` |
| `vX.Y.Z-rc.N` | Release Candidate | `v2.0.0-rc.1` |

---

## 自更新兼容与便携包发布纪律

### Manifest revision

- `version.txt` 是正式 Release 基线；tag 后的 `main` hotfix 通过 exact SHA 与 commits-ahead 展示，不要把合成版本写回 `version.txt`。
- 更改更新协议、持久化状态或目标验证方式，且旧 updater 无法安全理解时，递增 `updateProtocolRevision`。
- 代码需要不同嵌入式 Python、PyTorch/CUDA、视频重建环境、COLMAP/ffmpeg 或其它便携运行时才能工作时，必须在同一个提交递增 `portableRuntimeRevision` 并发布新完整包。不得让 Latest 先进入 `main` 再补 revision。
- 每个 Stable/Latest 目标都必须包含有效 `update-manifest.json`、匹配的 `supportedPortableTargets` 和当前 `frontend/dist/`。runtime revision 不一致时的唯一自动行为是拒绝代码更新并提示完整包。

### Windows 完整便携包

- 包含本功能的下一次完整便携版是自更新 **bootstrap** 版本；`v1.3.0` 及更早便携包必须最后下载一次完整包，不能宣称旧脚本可原地获得新 updater/MinGit/managed worktree。
- 三个 target（`cu128-rtx50`、`cu126-mainstream`、`cu128-rtx50-video-recon`）都要在 package root 建立 exact source SHA 的干净受管 worktree，并把 runtime/user 路径保持 ignored/untracked。代码 checkout 不得管理 Python/CUDA/video env、模型、workspace、配置、日志或包内工具。
- 固定使用官方标准 x64 MinGit `v2.55.0.windows.3` 的 `MinGit-2.55.0.3-64-bit.zip`，构建前验证 SHA256 `f48e2d2dc74a24454adc6d8fd0ac25bf9c2386f19cfb06202b9465aaad4f9f05`。不得改用实验性 BusyBox asset、浮动 latest URL 或未经校验缓存。
- 完整复制 MinGit 到 `.sharp-gui-tools/git/`，保留根 `LICENSE.txt`、`mingw64/share/licenses/`、`usr/share/licenses/` 及 archive 中其它 license/notice；同时打包根 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)。更新 MinGit pin 时，版本、asset、digest、release/source tag、许可清单和 notice 必须同批更新。
- `portable-package.json` 至少记录 exact Sharp GUI commit、正式 Release 基线、canonical repo、package target、portable/update protocol revision、MinGit version/digest/相对 executable；不得记录凭据或构建机绝对路径。
- 发布说明继续提供每个便携 ZIP 的 SHA256 和外部网盘入口，并明确 bootstrap 边界、Stable/Latest 风险、保留范围、自动 rollback 以及 runtime revision 不一致需完整包。

### 发布验证

先运行 `build_portable_release.bat -Version <version> -PlanOnly` 审核 target/source/runtime/MinGit 矩阵；实际构建后按 `.agents/rules/testing.md` 的“便携包自更新 smoke matrix”完成 ZIP、clean extract、无系统 Git/Python、兼容更新、不兼容拒绝、启动和 rollback 验证。只看到构建脚本退出 0 不等于发布合格。

---

## 用户端更新

Settings 与脚本统一使用 Stable（最新正式 GitHub Release）或 Latest（`main` exact commit）：

```bash
# 检查，不修改文件
./update.sh --channel stable --check
./update.sh --channel latest --check

# 应用已验证目标（可加 --yes 跳过交互确认）
./update.sh --channel stable
./update.sh --channel latest
```

Windows 使用等价的 `update.bat` 参数。CLI 只支持 `--channel`、`--check`、`--yes`；**`--pre` 与 `--rollback` 已废除**，不要在文档或 release note 中出现。更新调用同一事务 updater：owner-only、active task/dirty/non-main 阻断、manifest compatibility gate、exact commit checkout、健康检查和失败自动 rollback；不再使用未验证 Release ZIP 覆盖安装。成功后没有手动回滚入口，只有目标验证失败时的自动恢复。

---

## 发布前检查清单

- [ ] 所有功能已完成并测试
- [ ] 前端构建成功（`./build.sh`）
- [ ] `frontend/dist/` 与当前源码一致，`update-manifest.json` revision/targets 正确
- [ ] 本地运行正常（`./run.sh`）
- [ ] README 更新（如有新功能）
- [ ] i18n 文件完整（en.json 和 zh.json key 一致）
- [ ] 无 TypeScript 编译错误
- [ ] 无 ESLint 错误
- [ ] Git 工作区干净（含未跟踪文件，`release.sh` / `release.bat` 会强制检查）
- [ ] `version.txt` 与将要打的 tag 完全一致，且由独立的 `chore(release)` 提交同步
- [ ] 本次是否改动运行时敏感文件（requirements / 安装器 / 便携构建脚本）？若是，`portableRuntimeRevision` 已递增且已计划发布新完整包
- [ ] 没有任何用户数据或运行时路径被误纳入版本管理（`git status --porcelain --untracked-files=all` 复核）
- [ ] 正式 Release 可被 Stable 解析；prerelease 不会成为 Stable
- [ ] 便携计划输出的 MinGit version/asset/SHA256 正确，完整 license trees 与 `THIRD_PARTY_NOTICES.md` 已进入 staging
- [ ] 三 target 的 managed worktree、runtime revision、无系统工具 self-update/rollback smoke 结果已记录
