# 自更新系统开发规范

本文面向 Sharp GUI 开发者和发布维护者。普通用户只需阅读 README 的“版本与更新”；修改更新后端、前端、便携包构建、依赖或发布流程时，按本文检查。

相关规范：

- [项目结构与运行时目录](project-overview.md)
- [后端服务与安全边界](backend-guide.md)
- [测试规范与便携包 smoke matrix](testing.md)
- [版本发布流程](../workflows/release.md)

## 1. 产品边界

自更新采用“固定大型运行环境 + Git 管理应用代码”的模式：

- Stable：规范仓库中版本号最高的正式 **vX.Y.Z** 标签，不包含 prerelease 标签。
- Latest：规范仓库 **main** 分支的最新精确提交。
- 只更新 Git 跟踪的应用文件；新增、删除、重命名和目录重构都由 Git 精确收敛。
- Python、PyTorch/CUDA、视频重建环境、模型、workspace、配置、证书、日志和包内工具不随代码更新替换。
- 目标验证或重启失败时自动恢复上一提交；不提供成功更新后的手动回滚产品入口。

源码安装与 Windows 便携包共用同一套检查和事务。普通 GitHub 源码快照或旧便携包没有受管 worktree，只显示版本状态，不能原地自更新。

不支持后台静默安装、任意仓库/分支、开发者本地修改自动合并、Legacy 前端更新，以及跨 **portableRuntimeRevision** 原地替换大型运行环境。

## 2. 关键文件

| 路径 | 职责 |
|------|------|
| [update-manifest.json](../../update-manifest.json) | 项目根目录中的更新协议与便携运行时兼容契约 |
| [backend/services/self_update.py](../../backend/services/self_update.py) | 安装识别、Git 目标解析、兼容判断、状态、事务和失败恢复 |
| [backend/routes/updates.py](../../backend/routes/updates.py) | status、check、apply API |
| [tools/update.py](../../tools/update.py) | CLI 与服务外更新 helper |
| [update.bat](../../update.bat)、[update.sh](../../update.sh) | 用户命令行入口 |
| [UpdateSettingsSection](../../frontend/src/components/layout/Settings/UpdateSettingsSection/UpdateSettingsSection.tsx) | Settings 中的精简更新界面 |
| [tools/build_portable_package.ps1](../../tools/build_portable_package.ps1) | 单包受管 worktree 与 MinGit 打包 |
| [tools/build_portable_release.ps1](../../tools/build_portable_release.ps1) | 三种便携包发布编排 |
| [tools/portable_update_common.ps1](../../tools/portable_update_common.ps1) | 两个打包脚本共用的 manifest、版本与 Git 校验 |
| [tools/check_update_compatibility.py](../../tools/check_update_compatibility.py) | runtime revision CI 守卫 |
| [.github/workflows/update-compatibility.yml](../../.github/workflows/update-compatibility.yml) | PR / main 兼容性检查 |

安装级状态位于 **.sharp-gui-update/**，便携包工具位于 **.sharp-gui-tools/**。两者不随 workspace 切换，也不得通过 **/files/** 暴露。

## 3. 支持的安装类型

| 类型 | 识别条件 | 行为 |
|------|----------|------|
| source | 项目根是受管 Git worktree | main 且 tracked 文件干净时可检查和安装 |
| portable | 受管 Git worktree + portable-package.json | 使用包内 Python 和 MinGit 更新 |
| release | 只有版本文件、没有受管 worktree | 仅显示状态，要求 Git 安装或新的完整包 |
| unknown | 元数据不足 | 禁止更新并显示具体原因 |

**update-manifest.json** 必须存在于当前安装根目录和目标提交根目录。当前安装缺失时连检查都禁止；目标缺失时保留当前版本并提示目标不兼容。

开发分支允许检查目标，但禁止一键安装；tracked dirty worktree、正在运行的生成任务和已有更新操作同样禁止安装。

## 4. 兼容清单

当前 schema：

~~~json
{
  "schemaVersion": 1,
  "application": "sharp-gui",
  "repository": {
    "slug": "lueluelue12138/sharp-gui",
    "url": "https://github.com/lueluelue12138/sharp-gui.git"
  },
  "defaultBranch": "main",
  "updateProtocolRevision": 1,
  "portableRuntimeRevision": 1,
  "minimumGitVersion": "2.30.0",
  "frontend": {
    "builtAssetsRequired": true,
    "entrypoint": "frontend/dist/index.html"
  },
  "supportedPortableTargets": [
    "cu128-rtx50",
    "cu128-rtx50-video-recon",
    "cu126-mainstream"
  ]
}
~~~

版本规则：

- **schemaVersion**：清单结构不兼容时调整。
- **updateProtocolRevision**：旧 updater 无法安全理解新事务协议时调整，并要求用户安装完整包。
- **portableRuntimeRevision**：Python、PyTorch/CUDA、原生依赖、安装器或便携构建结果变化时递增，并发布完整包。
- 普通前后端源码、路由、组件和目录重构通常不调整 runtime revision，但目标必须提交新的 **frontend/dist**。

目录或文件新增、删除、改名、拆分和合并不需要额外适配；Git reset 到 exact target 会同步整个 tracked tree。例外是把运行时/用户数据误纳入 Git，或把后端需要的文件移到打包排除范围，这些必须在合并前修正。

## 5. 更新流程

1. status 读取当前版本、commit、安装类型、分支、dirty 和能力。
2. check 通过规范仓库 Git refs 解析目标：
   - Stable 使用最高正式 **vX.Y.Z** 标签；
   - Latest 使用 **refs/heads/main**。
3. 拉取目标到本地更新 ref，读取目标清单和 **frontend/dist/index.html**，计算与当前提交的关系。
4. 仅持久化最近一次检查得到的 exact SHA、通道、兼容结果和时间；不使用 GitHub REST、ETag 或客户端 target token。
5. apply 只接受通道，并要求存在未过期的服务端检查结果。
6. 外部 helper 等待 Flask 停止，再次 fetch 并校验 exact SHA、清单、受保护路径和当前 HEAD。
7. 记录 previous SHA，更新 tracked tree，执行 Python compile/import、前端入口和包元数据健康检查。
8. 启动新服务并验证 commit；失败时自动 reset 到 previous SHA、验证并重新启动旧版本。
9. **.sharp-gui-update/state.json** 原子保存阶段；启动时按实际 HEAD 对账未完成操作。

前端只展示当前版本、通道、目标、明确阻断原因、检查/安装按钮和重启进度。服务重启造成的短暂断线是正常流程，页面在新实例和目标 commit 可见后刷新。

## 6. API 与 CLI

| API | 权限 | 说明 |
|-----|------|------|
| GET /api/updates/status | Unlocked | 脱敏版本、能力、候选和操作状态 |
| POST /api/updates/check | Owner | 请求体仅允许 channel |
| POST /api/updates/apply | Owner | 请求体仅允许 channel，使用最近检查的 exact SHA |

CLI 与 UI 共用管理器和事务：

~~~bash
./update.sh --channel stable --check
./update.sh --channel stable
./update.sh --channel latest --check
./update.sh --channel latest
~~~

Windows 使用相同参数的 **update.bat**。不再维护 **--pre**、**--rollback** 或 Release archive 覆盖兼容入口。

## 7. 安全约束

- check/apply 只能由真实 localhost owner 发起；不能信任 X-Forwarded-For 等客户端头提权。
- 客户端不能提交 URL、仓库、分支、tag、SHA、命令或文件路径。
- Git 使用参数列表、非交互环境、规范仓库 URL 和明确 executable；不修改全局 PATH 或 Git 配置。
- apply 在文件 mutation 前重新检查任务、锁、branch、dirty、当前 HEAD、目标时效和兼容清单。
- 响应不得包含绝对路径、Git 命令、凭据、原始异常栈或远端 stderr。
- config.json、证书、日志、workspace、模型、Python/runtime、.sharp-gui-tools/、.sharp-gui-update/ 和视频重建环境不得被目标提交跟踪。

## 8. 便携包与 MinGit

Windows 便携包固定内置经 SHA256 校验的 MinGit，并记录版本、来源、asset、digest 和 license。运行时优先：

1. 包内 Python；
2. .sharp-gui-tools/git/cmd/git.exe；
3. 源码安装才允许使用受支持的系统 Git。

打包时创建与 source SHA 一致的干净受管 worktree，并把用户/运行时路径写入本地 exclude。不得把维护者凭据、源机器绝对路径、源仓库 remote 配置或全局 Git 设置带入包。

**tools/portable_update_common.ps1** 只承载两个构建脚本真正共享的只读校验，MinGit 下载、校验、license 和 worktree 初始化仍由单包构建脚本负责。

## 9. CI 防线

**update-compatibility.yml** 比较 base/head 的变更路径：

- 普通应用源码和 frontend/dist 变化不要求递增 portableRuntimeRevision。
- requirements、环境锁文件、安装器、PyTorch/视频环境工具、便携构建器和共享构建助手变化时，必须递增 revision。
- revision 不得降低。
- 仓库首次引入 update-manifest.json 时按 bootstrap 处理。

如 CI 要求 bump，必须同步发布新的完整便携包；不能为了通过检查随意递增而不发布对应运行时。

## 10. 验证清单

修改自更新时至少执行：

~~~bash
python -m pytest tests/test_self_update.py tests/test_self_update_routes.py \
  tests/test_self_update_transaction.py tests/test_self_update_recovery.py \
  tests/test_update_cli.py tests/test_update_compatibility_guard.py -q
cd frontend
npm run lint
npm run build
~~~

并检查：

- [ ] Stable/Latest 解析到规范仓库可信 exact SHA，正式标签不混入 prerelease。
- [ ] 当前和目标均包含有效清单，目标包含最新 frontend/dist。
- [ ] dirty、开发分支、活动任务、并发操作和过期候选均安全拒绝。
- [ ] tracked 增删改名精确收敛，用户/runtime marker 保持不变。
- [ ] apply、重启健康检查、自动失败恢复和中断对账均有覆盖。
- [ ] owner-only 权限、响应脱敏和客户端输入边界未放宽。
- [ ] build_portable_release.bat -Version <version> -PlanOnly 三种目标通过。
- [ ] MinGit 版本、SHA256、license 和包内路径保持可验证。
- [ ] 中英文 UI/README、本文、生成前端资产与实现同步。

完整 clean-extract 和视频重建 gate 以 [testing.md](testing.md) 为准。
