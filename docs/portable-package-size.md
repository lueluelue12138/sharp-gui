# Windows 便携包体积与打包

完整离线包同时提供单图 SHARP 推理，以及视频包中的 COLMAP、Brush、FFmpeg。
单图推理需要 PyTorch/CUDA 和官方 `sharp_2572gikvuh.pt` 权重；该权重实际约 **2.62 GiB**，不是 500 MB。
仅提供原生视频重建工具的安装程序不包含这些单图依赖，不能直接按下载大小比较。

## 当前裁剪边界

构建器只裁剪包副本，开发环境与旧发布包不变：

- 不打入 `frontend/node_modules`；界面和独立 HTML 分享使用已构建的 `frontend/dist`。
- 移除 PyTorch 的 `dnnl.lib`、Protobuf 与 Kineto 静态开发库，保留扩展编译需要的导入库和头文件。
- 对已验证的 PyTorch 2.8.0 / CUDA 12.8、12.6 组件，裁剪当前应用未使用的 `curand64_10.dll` 与多 GPU 求解库 `cusolverMg64_11.dll`；保留矩阵运算、卷积、FFT、稀疏求解、NVRTC 和各 GPU 架构。
- 当前视频路线使用 SIFT；仅对已验证 COLMAP 组件裁剪可选 ONNX CUDA provider 及未使用的 cuRAND，保留 COLMAP 直接依赖的 ONNX 核心和 Qt 库。
- 移除 COLMAP 的独立 `*_test.exe` 和未使用的 `ffplay.exe`，保留重建程序、FFmpeg、FFprobe 和许可资料。
- 原始模型权重保持逐字节一致，不做 FP16/INT8 转换，不改变训练参数或模型效果。
- 固定 Brush 上游发行物、MinGit 完整许可证树和来源校验继续保留。

裁剪清单由 `tools/trim_portable_runtime.py` 维护，默认只列计划；构建器对具备便携包标识的 staging 目录显式执行裁剪。
脚本拒绝源码工作区、符号链接和 Windows junction。包元数据的 `runtimeLayout` 记录清单版本和移除量。
原生库裁剪同时校验保留组件的源码/原生文件整体指纹与候选库 SHA256；未知版本、额外原生文件或内容变动时保留所有候选库。
已采用的配置写入 `runtimeLayout.nativeProfiles`。后续增加学习特征或其它 GPU 工具时，必须重新核查这些裁剪边界。
裁剪规则变化属于运行时变更，必须递增 `portableRuntimeRevision` 并重新构建完整包，不能借助代码更新改动用户已有运行时。

## 压缩选项

默认使用压缩等级 7 的 ZIP，保持常见解压流程；允许更小的 7z/LZMA2 实心压缩包：

```bat
build_portable_release.bat -PlanOnly
build_portable_release.bat -OutputDir G:\releases\slim-zip
build_portable_release.bat -ArchiveFormat 7z -OutputDir G:\releases\slim-7z
```

7z 格式可使用 7-Zip 解压。两种格式均包含完整运行时和原始权重，解压后启动方式相同。
实心压缩需要更长的打包时间；发布前应完成完整性测试和全新目录解压验证。
ZIP 与 7z 应放入不同输出目录，避免同名校验文件和发布清单混用。
`-CompressionLevel 1` 仍可用于本地快速试包。

## 验证要求

除了单元测试、更新兼容性与包内来源校验，还应在不借用系统 Python/Git/视频工具的环境中验证：

1. 单图 CUDA 推理，并与未裁剪基准比较输出。
2. 视频抽帧、相机配准、Brush 训练、PLY/SPZ 导出。
3. 首页、模型/媒体列表、模型编辑保存和独立 HTML 分享导出。
4. 最终压缩包完整性、全新目录解压后的启动与功能检查。

体积统计必须区分下载大小和解压后大小；短视频低步数 smoke 只验证链路，不代表画质或性能基准。
不要通过删除单图功能、延迟下载权重、降低模型精度或偷偷替换重建引擎来宣称完整包瘦身。

## English summary

The offline package includes the original 2.62 GiB SHARP checkpoint and its PyTorch/CUDA runtime.
The video edition also includes COLMAP, Brush and FFmpeg. The build removes frontend development
dependencies, unused oneDNN/Protobuf/Kineto static libraries, standalone COLMAP test executables
and FFplay. Verified PyTorch runtimes also omit unused host cuRAND and multi-GPU solver libraries;
the verified SIFT-only COLMAP package omits the optional ONNX CUDA provider and unused cuRAND.
Native removal requires matching component fingerprints and candidate hashes; unknown or changed
components retain their libraries. Model weights, required runtime libraries, headers, licenses and
reconstruction settings are preserved.

ZIP compression level 7 remains the default. Use `-ArchiveFormat 7z` for a smaller solid LZMA2
archive, in a separate output directory. Extract with 7-Zip and run `portable-run.bat` as usual.
Runtime changes require a new complete package. Verify clean extraction, CUDA image inference,
video reconstruction, model editing, HTML export and update compatibility before distribution.
