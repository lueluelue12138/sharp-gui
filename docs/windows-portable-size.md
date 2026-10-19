# Windows 便携包体积盘点与精简方案

核对日期：2026-10-19；Sharp GUI 基线 `bc86e535`，portable runtime revision 3；上游固定标签 OOOSplat `0.6.0`（`c49963e61bf8636409db3af79422f724eec001c6`）。

## 结论与口径

完整包可以精简，但保留当前单图 ML-Sharp、视频重建和离线使用能力时，不能仅靠删缓存压到 200 MB。单图使用的 PyTorch/CUDA 与模型权重是主要差异。视频专用包或首次联网安装依赖的启动器可以更小，但属于另一种发行形态。

OOOSplat 官方 Windows 安装器展示为 **229 MB**，SHA256 为 `779058a55d58ffda3ccecf5dd89ef4dc7eee188603acb08f2f074f02279c3ac4`。这是压缩安装器的下载大小，不是安装后体积。[官方发布资产](https://github.com/ooolabdev/ooosplat/releases/expanded_assets/0.6.0)

原来的 `sharp-gui-portable-validation` 和验证包已删除，本轮没有重测它，也没有重新下载或解压大包。下面全部为**当前构建源组件的逻辑文件字节**，包含部分构建时会排除的缓存；不同目录复制到同一目标时还会覆盖，所以不能把汇总当成最终 ZIP 或精确解压体积。1 GiB = 1,073,741,824 字节，1 MiB = 1,048,576 字节。

## 本机实测

| 组件 | 字节数 | 约合 | 说明 |
| --- | ---: | ---: | --- |
| 主 venv 全部 site-packages | 8,002,212,867 | 7.45 GiB | 当前图片推理环境，含缓存 |
| 其中 torch | 7,423,459,864 | 6.91 GiB | 是上一项的子集，不能再次相加 |
| ML-Sharp 权重 | 2,809,738,232 | 2.62 GiB | `sharp_2572gikvuh.pt`，完整离线图片推理使用 |
| 基础 Python 整体 | 478,391,933 | 456.23 MiB | 构建器先复制它，再覆盖 venv 依赖 |
| frontend/node_modules | 249,916,769 | 238.34 MiB | 包含开发工具、缓存及分享所用运行时资源 |
| 原生 COLMAP | 807,794,918 | 770.37 MiB | bin 与 plugins 等 |
| 固定 Brush 0.3.0 | 317,562,179 | 302.85 MiB | 两份相同 exe 及许可/来源资料 |
| FFmpeg 工具目录 | 304,454,656 | 290.35 MiB | ffmpeg、ffprobe、ffplay 各一份静态 exe |

除 torch 子项外，上述选定目录合计 **12,970,071,554 字节，约 12.08 GiB**，不含其余应用代码、MinGit、Git 对象等。它只解释当前来源，不证明历史 10 GiB ZIP 的组成。

额外确认：

- 基础 Python 的 `Lib/site-packages` 排除 `__pycache__` 后为 355,037,591 字节。其中相对于主 venv **没有同名目标文件、会残留的路径**合计 308,668,241 字节（294.37 MiB），包括构建机附带的文档/表格处理依赖。不是 Sharp GUI 自动安装的必需依赖，也不能把整个基础 Python 目录当作可删除内容。
- `torch/lib` 的 23 个 `.lib` 合计 2,815,153,848 字节；其中 `dnnl.lib` 为 2,325,850,314 字节（2.17 GiB）。对这一个文件以 zlib 流抽样，level 1 输出 511,884,271 字节（488.17 MiB），level 6 输出 426,108,092 字节（406.37 MiB）。**这不是完整 ZIP 测试**，但说明不能把 2.17 GiB 直接当成下载节省量；提高压缩等级的该样本差约 81.80 MiB。
- Brush 根目录与 `upstream-release/` 下的 `brush_app.exe` 都是 158,758,912 字节，SHA256 均为 `37e46cbf808b9983dd15a5f9a25328dbe43e7e06d53c4f59fbeaeb10e3a5b34a`。来源归档副本用于保留原始许可/资料；去重需同步来源策略，不能删除整个目录。
- 离线 HTML 导出实际读取五项资源：`three.module.js`、`three.core.js`、`OrbitControls.js`、`Pass.js`、`spark.module.js`，当前合计 7,428,396 字节（7.08 MiB）。它们由 `backend/services/export_html.py` 读取，不能因首页已打包进 dist 就删除全部 node_modules。

## 与 OOOSplat 0.6.0 的实际差异

| 项目 | Sharp GUI 当前构建源 | OOOSplat 0.6.0 固定配置 |
| --- | --- | --- |
| 应用与图片能力 | Python/Flask；ML-Sharp 单图生成；模型库、图库、视频、分享 | Tauri/Rust 的本地多视图/视频训练应用；未打包我们的 ML-Sharp 单图推理环境和权重 |
| 图片推理依赖 | PyTorch `2.8.0+cu128`、torchvision `0.23.0+cu128`、gsplat `1.5.3` | 原生 Brush 训练，不依赖这套 Python 推理链 |
| Brush | 官方 `0.3.0`，来源 commit `3edecbb…`，含原 viewer 程序 | OOOBrush `1.0.0`，commit `866a7d6…`，仅 headless CLI |
| COLMAP | 新装脚本固定 4.0.4；本机复用旧原生安装，实际是 `4.1.0.dev0 / 5b76f53 / CUDA` | 自建 4.2.1，CLI-only SIFT/SfM，排除 GUI/ONNX/MVS；有 CUDA/Caspar/Ceres CPU 回退 |
| FFmpeg | 本机 Gyan 8.1 essentials 静态 GPL 构建，复制整个 bin | BtbN LGPL shared 8.1 固定构建 |
| 压缩 | ZIP 默认 level 1 | NSIS，bzip2 |

依据：[上游 Cargo 配置](https://github.com/ooolabdev/ooosplat/blob/0.6.0/src-tauri/Cargo.toml)、[固定引擎清单](https://github.com/ooolabdev/ooosplat/blob/0.6.0/engines/manifest.json)、[NSIS 配置](https://github.com/ooolabdev/ooosplat/blob/0.6.0/src-tauri/tauri.conf.json)、[Windows 构建与安装检查](https://github.com/ooolabdev/ooosplat/blob/0.6.0/.github/workflows/windows.yml)。

不能把上游运行时直接复制过来：其 COLMAP 清单声明 CUDA 13.2、最低 Windows 驱动 580.00、最低计算能力 7.5；Brush CLI 和训练参数也不同。升级需要显卡兼容和同素材画质验证。此次没有改引擎、分辨率、训练预算、模型权重或画质。

## 建议实施顺序

以下均为**待实施、待完整包验证的方案**。本轮仅增加盘点工具和证据，现有打包结果保持原样。

### 第一阶段：保留所有能力，裁掉与运行无关的内容

| 候选 | 当前可核对的逻辑节省上限 | 具体做法与验收 |
| --- | ---: | --- |
| 基础 Python 的额外 site-packages | 本机约 294 MiB | 在独立 staging 中复制解释器/标准库时排除基础 `Lib/site-packages`，只装入独立 venv 的锁定运行依赖。先确认 `include-system-site-packages=false`；用干净环境完成图片、视频、媒体、分享和更新测试，防止开发机依赖偶然补缺。 |
| 全量前端依赖 | 本机约 231 MiB | 给分享运行时建立明确资源清单与版本/哈希，从 node_modules 仅打包五项必需资源和相应完整许可；为后续更新保持稳定路径/契约。验证断网打开导出 HTML 的旋转、缩放、动画和全部模型格式。开发依赖和 `.vite/.tmp` 不进入包。 |
| ffplay | 97.79 MiB | 当前启动与处理链只调用 ffmpeg/ffprobe；在 staging 中排除 ffplay，保留真实解码库与完整来源/许可。验证照片尺寸/视频封面、H.264/HEVC/10-bit、AAC 与异常音轨、视频重建输入。若换 shared FFmpeg，必须重新核对 DLL 闭包和编解码器覆盖，不能简单换 LGPL 包就宣布等价。 |
| Brush exe 重复副本 | 151.40 MiB | 保留唯一不变的正式 exe、哈希和全部上游许可/附带说明；调整来源/安装清单策略后，只在 staging 排除重复 exe。原开发安装保持不动。必须重新验证安装校验和打包 smoke。 |

这四项仅是本机候选合计约 **775 MiB 未压缩**，不能承诺下载包能减少同等大小。

### 第二阶段：重点核实大链接库和压缩策略

- `dnnl.lib` 优先做独立 staging 对照候选；不删除任何开发机文件。它不是运行时 DLL，但不能据此批量移除全部 `.lib`、headers、CUDA DLL 或 CPU 回退。PyTorch 的 Windows C++ 扩展链接过程明确使用 `c10.lib`、`torch_cpu.lib`、`torch_cuda.lib`、`torch_python.lib` 等；gsplat 的扩展编译和图像渲染路径必须用真实生成任务验证。[PyTorch 2.8.0 扩展链接实现](https://github.com/pytorch/pytorch/blob/v2.8.0/torch/utils/cpp_extension.py)
- 对相同 staging 的 ZIP level 1/6/9 做字节、打包时间、解压时间比较，再决定发行默认等级。抽样证明存在收益，不代表全部二进制和浮点权重都有同样压缩比。保留 ZIP 格式可避免新增解压器要求。
- 若要自建 headless Brush 或 CLI-only COLMAP，作为单独引擎工作：固定源码、工具链、架构、哈希与许可，测试 GPU/CPU 回退和同视频画质，不能为了省体积顺带换用未验证训练配方。

### 第三阶段：需要接近小安装器体积时再拆发行形态

1. **完整离线包继续保留**：下载后无需再安装权重/PyTorch，保留当前全部能力；不能宣称能做到 229 MB。
2. **视频专用包**：不含 ML-Sharp 权重和 PyTorch，保留 Brush/COLMAP/FFmpeg、编辑器、图库、分享；需要独立能力标识与 UI 禁用/安装单图入口。Flask 路由和依赖须先验证能完全脱离 Torch，不是直接删目录。
3. **按需安装版**：小主程序首次使用单图功能时再下载可校验、可断点恢复的运行环境/权重；必须明确联网与额外空间要求，不能再称为完整离线便携包。

当前用户更重视画质，建议先做第一阶段及 `dnnl.lib` 的隔离验证，再决定是否增加不同发行版。

## 完整包实施的发布门槛

- 修改安装器、构建脚本或裁剪大型运行时，要与 `portableRuntimeRevision` 递增和新完整包同批交付；不能让普通代码更新在旧包内任意裁剪环境。本轮没有改这些文件或递增版本。
- 第一轮只构建 RTX 50 / CUDA 12.8 视频重建包，记录生成的 exact commit、依赖清单、压缩/解压字节及 SHA256；验证通过再扩展 RTX 50 核心和主流 NVIDIA 核心包。不能据本机 RTX 50 验证推断所有显卡可用。
- 先核对磁盘剩余空间。staging、ZIP 和解压验证副本不要同时常驻；所有清理仅限该轮创建且已核对绝对路径的目录，不能碰原工作区和开发运行环境。
- 用净化 PATH 的解压副本验证 CUDA、图片生成及渲染、视频完整链路、音轨/缩略图、模型编辑保存、断网 HTML 分享和受管更新。记录与当前配方相同的训练分辨率/帧覆盖/质量结果。
- 比较前后文件清单，保留 Python/PyTorch/CUDA、FFmpeg、COLMAP、Brush、Three.js/Spark、MinGit 及其传递依赖的完整许可/通知；不能把所有 LICENSE/NOTICE 或 upstream-release 一并裁掉。

## 可复现盘点

新工具只读，使用 Python 标准库；没有清理或下载选项。

```powershell
# 对已有发布 ZIP：读取目录，不额外解压大包
.\venv\Scripts\python.exe tools/audit_portable_size.py --archive 'C:\releases\sharp-gui-video-portable.zip'

# 对明确指定的当前源组件：不扫描 inputs/outputs 或其它磁盘
.\venv\Scripts\python.exe tools/audit_portable_size.py --component torch=venv/Lib/site-packages/torch --component frontend_dependencies=frontend/node_modules --component colmap=.sharp-gui-tools/colmap --component brush=.sharp-gui-tools/brush/v0.3.0
```

组件模式仅汇总选定路径逻辑字节，重叠根会拒绝，内部链接/重解析点跳过并计数。ZIP 模式的 `archive_bytes` 是完整归档文件大小，`compressed_payload_bytes` 是成员压缩载荷之和（不含 ZIP 头/目录），`logical_bytes` 是成员逻辑大小之和。目录/ZIP 分类不暴露成员文件名或源绝对路径。无法完整读取时返回非零退出，不把缺失按零成功报告。

ZIP 工具只检查元数据，**不是 CRC、SHA256 或解压完整性验证**；发布仍需原有 SHA256 和归档测试。
