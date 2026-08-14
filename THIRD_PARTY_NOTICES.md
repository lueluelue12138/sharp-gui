# Third-Party Notices / 第三方声明

Sharp GUI source code is distributed under the root [MIT License](LICENSE). Third-party software and models keep their own licenses; the Sharp GUI license does not replace or broaden those terms.

Sharp GUI 源代码适用仓库根目录的 [MIT License](LICENSE)。第三方软件与模型继续适用各自许可证，Sharp GUI 的许可证不会替代或扩大这些授权范围。

## Bundled MinGit / 内置 MinGit

Windows full portable bundles produced by the self-update bootstrap release and later include the following unmodified standard x64 MinGit distribution for non-interactive code updates:

| Field | Recorded value |
|---|---|
| Project | [Git for Windows — MinGit](https://gitforwindows.org/mingit.html) |
| Version / tag | `v2.55.0.windows.3` |
| Official asset | `MinGit-2.55.0.3-64-bit.zip` (standard x64; not the experimental BusyBox variant) |
| SHA256 | `f48e2d2dc74a24454adc6d8fd0ac25bf9c2386f19cfb06202b9465aaad4f9f05` |
| Official release | [git-for-windows/git v2.55.0.windows.3](https://github.com/git-for-windows/git/releases/tag/v2.55.0.windows.3) |
| Asset download | [MinGit-2.55.0.3-64-bit.zip](https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.3/MinGit-2.55.0.3-64-bit.zip) |
| Corresponding source tag | [git-for-windows/git tree at v2.55.0.windows.3](https://github.com/git-for-windows/git/tree/v2.55.0.windows.3) |
| Source archive | [v2.55.0.windows.3 source tarball](https://github.com/git-for-windows/git/archive/refs/tags/v2.55.0.windows.3.tar.gz) |

The portable builder must verify the recorded SHA256 before extraction and copy the complete MinGit distribution into `.sharp-gui-tools/git/`. Do not strip or rewrite its license and notice inventory. In every distributed portable package this includes, at minimum:

- `.sharp-gui-tools/git/LICENSE.txt`
- `.sharp-gui-tools/git/mingw64/share/licenses/`
- `.sharp-gui-tools/git/usr/share/licenses/`
- any additional component `LICENSE`, `COPYING`, or `NOTICE` files present in the official archive

Git is licensed under GPLv2, while other programs and libraries shipped by Git for Windows retain the licenses recorded in that distribution. Consult the preserved files for the authoritative terms of each component. Release metadata must also record the MinGit version, asset name, SHA256, official release/source references, and package-relative executable path.

完整便携包构建时必须先校验上述 SHA256，再原样保留 MinGit 的完整许可清单。不得仅复制 `git.exe`、删除许可树，或用 PATH 中的系统 Git 代替已记录的包内工具。

## ML-Sharp Model License Boundary / ML-Sharp 模型许可边界

The Sharp GUI MIT License applies to Sharp GUI code only. It does **not** license the ML-Sharp models. Those models remain subject to Apple's separate [ML-Sharp Model License](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL), which restricts the models to non-commercial use.

Sharp GUI 的 MIT 许可证只适用于 Sharp GUI 代码，**不覆盖 ML-Sharp 模型**。ML-Sharp 模型继续适用 Apple 单独的 [模型许可证](https://github.com/apple/ml-sharp/blob/main/LICENSE_MODEL)，仅限非商业用途。
