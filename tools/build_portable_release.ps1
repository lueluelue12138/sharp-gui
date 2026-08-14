param(
    [string]$Version = "",
    [string]$OutputDir = "",
    [string]$MinGitCacheDir = "",
    [int]$CompressionLevel = 1,
    [switch]$PlanOnly,
    [switch]$AllowLocalVersion,
    [switch]$CleanBuildVenvs,
    [switch]$CleanOldArtifacts,
    [switch]$SkipArchiveTest,
    [switch]$SkipCu126,
    [switch]$SkipCu128,
    [switch]$SkipVideoRecon
)

$ErrorActionPreference = "Stop"

$script:CanonicalRepository = "https://github.com/lueluelue12138/sharp-gui.git"
$script:MinGitVersion = "2.55.0.windows.3"
$script:MinGitReleaseTag = "v2.55.0.windows.3"
$script:MinGitAssetName = "MinGit-2.55.0.3-64-bit.zip"
$script:MinGitSha256 = "f48e2d2dc74a24454adc6d8fd0ac25bf9c2386f19cfb06202b9465aaad4f9f05"
$script:MinGitUrl = "https://github.com/git-for-windows/git/releases/download/$($script:MinGitReleaseTag)/$($script:MinGitAssetName)"
$script:MinGitExecutableRelativePath = ".sharp-gui-tools\git\cmd\git.exe"
$script:SupportedManifestSchemaVersion = 1
$script:SupportedUpdateProtocolRevision = 1

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message"
}

function Fail {
    param([string]$Message)
    Write-Host "[错误] $Message" -ForegroundColor Red
    exit 1
}

. (Join-Path $PSScriptRoot "portable_update_common.ps1")

function Get-PortableUpdateContext {
    param(
        [string]$Root,
        [string]$Version,
        [bool]$AllowVersionMismatch
    )

    $sourceRevision = Get-SourceRevision -Root $Root
    $sourceVersion = Get-SourceVersion -Root $Root -SourceRevision $sourceRevision
    if ($sourceVersion -ne $Version) {
        if (-not $AllowVersionMismatch) {
            Fail "source revision 的 version.txt ($sourceVersion) 与 -Version ($Version) 不一致"
        }
        Write-Info "本地测试版本标签 '$Version' 与 source version '$sourceVersion' 不同；元数据仍以 source version 为准。"
    }

    $releaseBaseline = Get-ReleaseBaseline -Root $Root -SourceRevision $sourceRevision -FallbackVersion $sourceVersion
    $commitsAhead = Get-CommitsAhead -Root $Root -ReleaseBaseline $releaseBaseline -SourceRevision $sourceRevision
    $compatibility = Get-UpdateCompatibilityInfo -Root $Root

    return [PSCustomObject]@{
        ManifestSource = $compatibility.ManifestSource
        SchemaVersion = $compatibility.SchemaVersion
        Application = $compatibility.Application
        Repository = $compatibility.Repository
        DefaultBranch = $compatibility.DefaultBranch
        SourceRevision = $sourceRevision
        SourceVersion = $sourceVersion
        ReleaseBaseline = $releaseBaseline
        CommitsAhead = $commitsAhead
        PortableRuntimeRevision = $compatibility.PortableRuntimeRevision
        UpdateProtocolRevision = $compatibility.UpdateProtocolRevision
        MinimumGitVersion = $compatibility.MinimumGitVersion
        BuiltAssetsRequired = $compatibility.BuiltAssetsRequired
        FrontendEntrypoint = $compatibility.FrontendEntrypoint
        SupportedPortableTargets = $compatibility.SupportedPortableTargets
    }
}

function Write-PortableUpdatePlanInfo {
    param([object]$Context)

    Write-Info "Source SHA: $($Context.SourceRevision)"
    Write-Info "Source version: $($Context.SourceVersion)"
    Write-Info "Release baseline: $($Context.ReleaseBaseline)"
    $commitsAheadText = if ($null -eq $Context.CommitsAhead) { "unknown" } else { [string]$Context.CommitsAhead }
    Write-Info "Commits ahead: $commitsAheadText"
    Write-Info "兼容清单: $($Context.ManifestSource) (schema=$($Context.SchemaVersion))"
    Write-Info "Portable runtime revision: $($Context.PortableRuntimeRevision)"
    Write-Info "Update protocol revision: $($Context.UpdateProtocolRevision)"
    Write-Info "Manifest minimum Git: $($Context.MinimumGitVersion)"
    Write-Info "MinGit: $($script:MinGitReleaseTag) standard x64 / $($script:MinGitAssetName)"
    Write-Info "MinGit URL: $($script:MinGitUrl)"
    Write-Info "MinGit SHA256: $($script:MinGitSha256)"
    Write-Info "MinGit executable: $($script:MinGitExecutableRelativePath)"
}


function Remove-DirectoryTree {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $longPath = if ($resolved.StartsWith("\\?\")) {
        $resolved
    } else {
        "\\?\$resolved"
    }
    Remove-Item -LiteralPath $longPath -Recurse -Force -ErrorAction Stop
}

function Resolve-SevenZip {
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Invoke-CommandChecked {
    param(
        [string]$Description,
        [scriptblock]$Command
    )

    Write-Step $Description
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Fail "$Description 失败，退出码 $LASTEXITCODE"
    }
}

function Get-ReleaseVersion {
    param([string]$Root, [string]$RequestedVersion)

    if (-not [string]::IsNullOrWhiteSpace($RequestedVersion)) {
        return ($RequestedVersion.Trim() -replace "^refs/tags/", "")
    }

    try {
        $sourceRevision = ([string](& git -C $Root rev-parse --verify HEAD 2>$null | Select-Object -First 1)).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -eq 0 -and $sourceRevision -match '^[0-9a-f]{40}$') {
            return (Get-SourceVersion -Root $Root -SourceRevision $sourceRevision)
        }
    } catch {
    }

    try {
        $tag = (& git -C $Root describe --tags --exact-match 2>$null).Trim()
        if (-not [string]::IsNullOrWhiteSpace($tag)) {
            return ($tag -replace "^refs/tags/", "")
        }
    } catch {
    }

    try {
        $tag = (& git -C $Root describe --tags --abbrev=0 2>$null).Trim()
        if (-not [string]::IsNullOrWhiteSpace($tag)) {
            return ($tag -replace "^refs/tags/", "")
        }
    } catch {
    }

    return "local-" + (Get-Date -Format "yyyyMMdd-HHmm")
}

function Test-VersionIsReleaseLike {
    param([string]$Version)
    return $Version -match '^v\d+\.\d+\.\d+([.-](rc|alpha|beta|preview)\.?\d*)?$'
}

function Test-PythonCuda {
    param([string]$PythonExe)

    $code = @'
import json
import sys
import warnings

try:
    warnings.filterwarnings("ignore")
    import torch
    payload = {
        "ok": True,
        "torch": getattr(torch, "__version__", ""),
        "cuda": getattr(getattr(torch, "version", None), "cuda", None),
        "cuda_available": bool(torch.cuda.is_available()),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else None,
        "arch_list": list(torch.cuda.get_arch_list()),
    }
    print(json.dumps(payload, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
    sys.exit(2)
'@

    $tmp = Join-Path $env:TEMP ("sharp-release-cuda-{0}.py" -f ([guid]::NewGuid().ToString("N")))
    Set-Content -LiteralPath $tmp -Encoding UTF8 -Value $code
    try {
        $raw = & $PythonExe $tmp
        if ($LASTEXITCODE -ne 0) {
            Fail "无法读取 PyTorch/CUDA 信息: $raw"
        }
        return $raw | ConvertFrom-Json
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-Cu126Venv {
    param(
        [string]$Root,
        [string]$BasePython
    )

    $venv = Join-Path $Root ".portable-venvs\cu126"
    $python = Join-Path $venv "Scripts\python.exe"

    if (-not (Test-Path -LiteralPath $python)) {
        Write-Step "创建 cu126 打包虚拟环境"
        & $BasePython -m venv $venv | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Fail "创建 cu126 虚拟环境失败"
        }
    }

    Write-Step "准备 cu126 打包依赖"
    & $python -m pip install --upgrade pip | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Fail "升级 cu126 pip 失败"
    }

    Push-Location (Join-Path $Root "ml-sharp")
    try {
        & $python -m pip install -r requirements.txt | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Fail "安装 ml-sharp requirements 到 cu126 环境失败"
        }
    } finally {
        Pop-Location
    }

    & $python -m pip install flask | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Fail "安装 Flask 到 cu126 环境失败"
    }

    & $python -m pip install --force-reinstall --no-deps torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Fail "安装 cu126 PyTorch 失败"
    }

    $info = Test-PythonCuda -PythonExe $python
    if (-not $info.ok) {
        Fail "cu126 PyTorch 导入失败: $($info.error)"
    }

    Write-Info "cu126 环境: torch=$($info.torch), cuda=$($info.cuda), device=$($info.device)"
    return $venv
}

function Invoke-PackageBuild {
    param(
        [string]$Root,
        [string]$Version,
        [string]$SourceRevision,
        [string]$Target,
        [string]$VenvDir,
        [string]$OutputDir,
        [string]$MinGitCacheDir,
        [int]$CompressionLevel,
        [bool]$SkipFrontendBuild,
        [bool]$PlanOnly,
        [bool]$AllowLocalVersion
    )

    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "tools\build_portable_package.ps1"),
        "-Version", $Version,
        "-ExpectedSourceRevision", $SourceRevision,
        "-Target", $Target,
        "-VenvDir", $VenvDir,
        "-OutputDir", $OutputDir,
        "-CompressionLevel", $CompressionLevel
    )

    if ($SkipFrontendBuild) {
        $args += "-SkipFrontendBuild"
    }
    if (-not [string]::IsNullOrWhiteSpace($MinGitCacheDir)) {
        $args += @("-MinGitCacheDir", $MinGitCacheDir)
    }
    if ($PlanOnly) {
        $args += "-PlanOnly"
    }
    if ($AllowLocalVersion) {
        $args += "-AllowLocalVersion"
    }

    & powershell @args
    if ($LASTEXITCODE -ne 0) {
        Fail "打包 $Target 失败"
    }
}

function Test-Archive {
    param([string]$SevenZip, [string]$ZipPath)

    Write-Step "测试 ZIP 完整性: $(Split-Path -Leaf $ZipPath)"
    & $SevenZip t $ZipPath
    if ($LASTEXITCODE -ne 0) {
        Fail "ZIP 完整性测试失败: $ZipPath"
    }
}

function Get-PortablePackageArchivePath {
    param(
        [string]$OutputDir,
        [string]$Version,
        [string]$Target
    )

    return Join-Path $OutputDir "sharp-gui-$Version-windows-$Target-portable.zip"
}

function Read-PortablePackageMetadata {
    param(
        [string]$SevenZip,
        [string]$ZipPath
    )

    $raw = @(& $SevenZip e -so -bd -y $ZipPath "portable-package.json" 2>$null)
    $exitCode = $LASTEXITCODE
    $metadataText = ($raw -join "`n").TrimStart([char]0xFEFF).Trim()
    if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($metadataText)) {
        Fail "便携 ZIP 缺少可读取的 portable-package.json: $ZipPath"
    }

    try {
        return $metadataText | ConvertFrom-Json
    } catch {
        Fail "便携 ZIP 中的 portable-package.json 无法解析: $ZipPath ($($_.Exception.Message))"
    }
}

function Assert-PortablePackageMetadata {
    param(
        [object]$Metadata,
        [string]$Target,
        [object]$UpdateContext,
        [string]$ZipPath
    )

    $checks = [ordered]@{
        sourceRevision = [string]$UpdateContext.SourceRevision
        target = $Target
        portableRuntimeRevision = [string]$UpdateContext.PortableRuntimeRevision
        updateProtocolRevision = [string]$UpdateContext.UpdateProtocolRevision
    }
    foreach ($name in $checks.Keys) {
        $property = $Metadata.PSObject.Properties[$name]
        if (-not $property) {
            Fail "便携 ZIP 元数据缺少 ${name}: $ZipPath"
        }
        if ([string]$property.Value -ne [string]$checks[$name]) {
            Fail "便携 ZIP 元数据 $name 不匹配: $($property.Value) != $($checks[$name]) ($ZipPath)"
        }
    }
}

function Assert-NoUnexpectedVersionArchives {
    param(
        [string]$OutputDir,
        [string]$Version,
        [string[]]$RequestedArchiveNames
    )

    $unexpectedArchives = @(Get-ChildItem -LiteralPath $OutputDir -File -Filter "sharp-gui-$Version-windows-*-portable.zip" -ErrorAction SilentlyContinue | Where-Object {
        $RequestedArchiveNames -notcontains $_.Name
    })
    if ($unexpectedArchives.Count -gt 0) {
        $names = ($unexpectedArchives.Name | Sort-Object) -join ", "
        Fail "输出目录含有本次未构建的同版本旧 ZIP，拒绝混入发布结果: $names。请使用 -CleanOldArtifacts 或单独的 -OutputDir。"
    }
}

function Write-ReleaseTemplate {
    param(
        [string]$OutputDir,
        [string]$Version,
        [object[]]$Packages,
        [object]$UpdateContext
    )

    $template = Join-Path $OutputDir "portable-release-template-$Version.md"
    $lines = New-Object System.Collections.Generic.List[string]

    $lines.Add("## Windows 完整便携包下载")
    $lines.Add("")
    $lines.Add("下载：[点击打开网盘文件夹](待填写网盘链接)")
    $lines.Add("")
    $lines.Add("网盘文件夹内包含 RTX 50 核心包、RTX 50 视频重建完整包和主流 NVIDIA 核心包，请按用途和显卡选择：")
    $lines.Add("")
    $lines.Add("| 适用显卡 | 下载文件 | SHA256 |")
    $lines.Add("|---|---|---|")

    $orderedPackages = $Packages | Sort-Object @{
        Expression = {
            switch ($_.Target) {
                "cu128-rtx50" { 0 }
                "cu128-rtx50-video-recon" { 1 }
                "cu126-mainstream" { 2 }
                default { 9 }
            }
        }
    }, Target

    foreach ($pkg in $orderedPackages) {
        switch ($pkg.Target) {
            "cu128-rtx50" {
                $label = "RTX 50 系列（核心包）"
            }
            "cu128-rtx50-video-recon" {
                $label = "RTX 50 系列（视频重建完整包）"
            }
            "cu126-mainstream" {
                $label = "RTX 50 以下主流 NVIDIA（核心包）"
            }
            default {
                $label = $pkg.Target
            }
        }

        $lines.Add(('| {0} | `{1}` | `{2}` |' -f $label, $pkg.File, $pkg.Hash))
    }

    $lines.Add("")
    $lines.Add('使用方式：下载匹配显卡和用途的 ZIP，校验 SHA256，解压后双击 `portable-run.bat`。')
    $lines.Add("")
    $lines.Add("- 只使用图片生成、模型浏览和图库功能：优先下载核心包。")
    $lines.Add("- 需要本地视频 3DGS 重建且使用 RTX 50 系列：下载视频重建完整包。")
    $lines.Add("")
    $lines.Add("> 当前完整便携包只支持 NVIDIA GPU，不提供纯 CPU 包；视频重建完整包仅按 RTX 50 / CUDA 12.8 路线发布，不代表所有 NVIDIA GPU 都已完成验证。")
    $lines.Add("")
    $lines.Add("### 自更新基线与工具来源")
    $lines.Add("")
    $lines.Add("- Release 基线：``$($UpdateContext.ReleaseBaseline)``")
    $commitsAheadText = if ($null -eq $UpdateContext.CommitsAhead) { "unknown" } else { [string]$UpdateContext.CommitsAhead }
    $lines.Add("- 相对 Release 基线新增提交数：``$commitsAheadText``")
    $lines.Add("- 源代码 revision：``$($UpdateContext.SourceRevision)``")
    $lines.Add("- Portable runtime revision：``$($UpdateContext.PortableRuntimeRevision)``")
    $lines.Add("- Update protocol revision：``$($UpdateContext.UpdateProtocolRevision)``")
    $lines.Add("- 受管仓库：$($UpdateContext.Repository)")
    $lines.Add("- 内置 Git：Git for Windows MinGit ``$($script:MinGitReleaseTag)`` standard x64")
    $lines.Add("  - 官方资产：[$($script:MinGitAssetName)]($($script:MinGitUrl))")
    $lines.Add("  - SHA256：``$($script:MinGitSha256)``")
    $lines.Add('  - 包内可执行文件：`.sharp-gui-tools\git\cmd\git.exe`；完整许可证目录随 MinGit 原样保留。')
    $lines.Add("")
    $lines.Add("这是首批带受管 Git 基线的自更新包；更旧的便携包需要先完整下载一次本包或后续完整包。Stable 对应最新正式 Release，Latest 对应 ``main`` 最新提交且测试程度较低。自动更新只应用 runtime revision 兼容的代码并支持回滚；Python、CUDA、PyTorch、COLMAP、ffmpeg 或视频重建运行时变化时，必须重新下载完整包。")
    $lines.Add("")
    $lines.Add("更新会保留配置、工作区输入/输出/模型资产和索引缓存、模型缓存、包内 Python/CUDA、MinGit、更新状态及可选视频重建环境。ZIP 本身仍须按上表 SHA256 校验后再使用。")

    Set-Content -LiteralPath $template -Encoding UTF8 -Value ($lines -join "`r`n")
    Write-Info "Release 模板: $template"
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = Get-ReleaseVersion -Root $root -RequestedVersion $Version
if (-not $AllowLocalVersion -and -not (Test-VersionIsReleaseLike -Version $version)) {
    Fail "当前解析到的版本号 '$version' 不像正式发布版本。请使用 -Version vX.Y.Z，或测试时加 -AllowLocalVersion。"
}
$updateContext = Get-PortableUpdateContext -Root $root -Version $version -AllowVersionMismatch:$AllowLocalVersion
$requestedTargets = @()
if (-not $SkipCu128) { $requestedTargets += "cu128-rtx50" }
if (-not $SkipVideoRecon) { $requestedTargets += "cu128-rtx50-video-recon" }
if (-not $SkipCu126) { $requestedTargets += "cu126-mainstream" }
if ($requestedTargets.Count -eq 0) {
    Fail "至少需要选择一个便携包目标，不能同时跳过全部目标"
}
foreach ($requestedTarget in $requestedTargets) {
    if (@($updateContext.SupportedPortableTargets | Where-Object { $_ -eq $requestedTarget }).Count -eq 0) {
        Fail "更新兼容清单不支持便携目标 '$requestedTarget'"
    }
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $root "portable-dist"
}
if ([string]::IsNullOrWhiteSpace($MinGitCacheDir)) {
    $effectiveMinGitCacheDir = Join-Path $root ".portable-venvs\downloads\mingit"
} elseif ([System.IO.Path]::IsPathRooted($MinGitCacheDir)) {
    $effectiveMinGitCacheDir = [System.IO.Path]::GetFullPath($MinGitCacheDir)
} else {
    $effectiveMinGitCacheDir = Join-Path $root $MinGitCacheDir
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

if ($CleanOldArtifacts -and -not $PlanOnly) {
    Write-Step "清理旧便携包产物"
    Get-ChildItem -LiteralPath $OutputDir -File -Filter "sharp-gui-*-windows-*-portable.zip" -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Get-ChildItem -LiteralPath $OutputDir -File -Filter "sharp-gui-*-windows-*-portable.sha256.txt" -ErrorAction SilentlyContinue |
        Remove-Item -Force
    Get-ChildItem -LiteralPath $OutputDir -File -Filter "portable-release-template-*.md" -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

$requestedArchivePaths = @{}
foreach ($requestedTarget in $requestedTargets) {
    $requestedArchivePaths[$requestedTarget] = Get-PortablePackageArchivePath `
        -OutputDir $OutputDir `
        -Version $version `
        -Target $requestedTarget
}
$requestedArchiveNames = @($requestedArchivePaths.Values | ForEach-Object { Split-Path -Leaf $_ })
if (-not $PlanOnly) {
    Assert-NoUnexpectedVersionArchives `
        -OutputDir $OutputDir `
        -Version $version `
        -RequestedArchiveNames $requestedArchiveNames
}

$mainPython = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $mainPython)) {
    Fail "未找到主虚拟环境 venv\Scripts\python.exe，请先运行 install.bat"
}
if (-not (Test-Path -LiteralPath (Join-Path $root "ml-sharp"))) {
    Fail "未找到 ml-sharp 目录，请先运行 install.bat"
}

$sevenZip = Resolve-SevenZip
if (-not $sevenZip) {
    Fail "未找到 7-Zip。请安装 7-Zip 后再生成完整大包。"
}

Write-Step "一键便携包发布计划"
Write-Info "版本: $version"
Write-Info "输出目录: $OutputDir"
Write-Info "压缩等级: $CompressionLevel"
Write-Info "7-Zip: $sevenZip"
Write-Info "MinGit 下载缓存: $effectiveMinGitCacheDir"
Write-PortableUpdatePlanInfo -Context $updateContext

if (-not $PlanOnly) {
    Assert-SourceRepositoryClean -Root $root
}

$mainInfo = Test-PythonCuda -PythonExe $mainPython
Write-Info "主环境: torch=$($mainInfo.torch), cuda=$($mainInfo.cuda), device=$($mainInfo.device)"

$cu126Venv = $null
if (-not $SkipCu126) {
    if ($PlanOnly) {
        $cu126Venv = Join-Path $root ".portable-venvs\cu126"
        Write-Info "cu126 环境: $cu126Venv (PlanOnly 不安装)"
    } else {
        $cu126Venv = Ensure-Cu126Venv -Root $root -BasePython $mainPython
    }
}

if ($PlanOnly) {
    if (-not $SkipCu128) {
        Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu128-rtx50" -VenvDir (Join-Path $root "venv") -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$false -PlanOnly:$true -AllowLocalVersion:$AllowLocalVersion
    }
    if (-not $SkipVideoRecon) {
        Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu128-rtx50-video-recon" -VenvDir (Join-Path $root "venv") -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$true -PlanOnly:$true -AllowLocalVersion:$AllowLocalVersion
    }
    if (-not $SkipCu126) {
        if (Test-Path -LiteralPath (Join-Path $cu126Venv "Scripts\python.exe")) {
            Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu126-mainstream" -VenvDir $cu126Venv -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$true -PlanOnly:$true -AllowLocalVersion:$AllowLocalVersion
        } else {
            Write-Step "打包计划"
            Write-Info "版本: $version"
            Write-Info "目标包: cu126-mainstream"
            Write-Info "依赖虚拟环境: $cu126Venv"
            Write-Info "输出 ZIP: $(Join-Path $OutputDir "sharp-gui-$version-windows-cu126-mainstream-portable.zip")"
            Write-PortableUpdatePlanInfo -Context $updateContext
            Write-Info "cu126 缓存环境尚不存在，真实运行时会自动创建。"
        }
    }
    Write-Host ""
    Write-Host "[OK] 一键发布计划检查完成，未生成 ZIP。" -ForegroundColor Green
    exit 0
}

Write-Step "清理本次请求目标的旧同名产物"
foreach ($archivePath in $requestedArchivePaths.Values) {
    $shaPath = [System.IO.Path]::ChangeExtension($archivePath, ".sha256.txt")
    Remove-Item -LiteralPath $archivePath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $shaPath -Force -ErrorAction SilentlyContinue
}

if (-not $SkipCu128) {
    Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu128-rtx50" -VenvDir (Join-Path $root "venv") -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$false -PlanOnly:$false -AllowLocalVersion:$AllowLocalVersion
}

if (-not $SkipVideoRecon) {
    $skipVideoFrontendBuild = -not $SkipCu128
    Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu128-rtx50-video-recon" -VenvDir (Join-Path $root "venv") -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$skipVideoFrontendBuild -PlanOnly:$false -AllowLocalVersion:$AllowLocalVersion
}

if (-not $SkipCu126) {
    Invoke-PackageBuild -Root $root -Version $version -SourceRevision $updateContext.SourceRevision -Target "cu126-mainstream" -VenvDir $cu126Venv -OutputDir $OutputDir -MinGitCacheDir $effectiveMinGitCacheDir -CompressionLevel $CompressionLevel -SkipFrontendBuild:$true -PlanOnly:$false -AllowLocalVersion:$AllowLocalVersion
}

$packages = @()
foreach ($target in $requestedTargets) {
    $zipPath = $requestedArchivePaths[$target]
    if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
        Fail "本次构建未生成请求的便携 ZIP: $zipPath"
    }
    $zip = Get-Item -LiteralPath $zipPath

    if (-not $SkipArchiveTest) {
        Test-Archive -SevenZip $sevenZip -ZipPath $zip.FullName
    }
    $metadata = Read-PortablePackageMetadata -SevenZip $sevenZip -ZipPath $zip.FullName
    Assert-PortablePackageMetadata `
        -Metadata $metadata `
        -Target $target `
        -UpdateContext $updateContext `
        -ZipPath $zip.FullName

    $hash = (Get-FileHash -LiteralPath $zip.FullName -Algorithm SHA256).Hash
    $shaPath = Join-Path $zip.DirectoryName ($zip.BaseName + ".sha256.txt")
    Set-Content -LiteralPath $shaPath -Encoding ASCII -Value "$hash  $($zip.Name)"
    $packages += [PSCustomObject]@{
        File = $zip.Name
        SizeGiB = [math]::Round($zip.Length / 1GB, 2)
        Hash = $hash
        Target = $target
    }
}
if ($packages.Count -ne $requestedTargets.Count) {
    Fail "便携包聚合数量不一致: $($packages.Count) != $($requestedTargets.Count)"
}

Write-ReleaseTemplate -OutputDir $OutputDir -Version $version -Packages $packages -UpdateContext $updateContext

if ($CleanBuildVenvs -and -not $PlanOnly) {
    Write-Step "清理临时打包环境"
    Remove-DirectoryTree -Path (Join-Path $root ".portable-venvs")
    Remove-DirectoryTree -Path (Join-Path $root ".portable-build")
} else {
    Remove-DirectoryTree -Path (Join-Path $root ".portable-build")
}

Write-Host ""
Write-Host "[OK] Windows 完整便携包一键打包完成" -ForegroundColor Green
$packages | Format-Table File, Target, SizeGiB, Hash -AutoSize
Write-Host ""
Write-Host "下一步：把 ZIP 和 .sha256.txt 上传到网盘，然后把 portable-release-template-$version.md 内容贴进 GitHub Release。"
Write-Host ""
Write-Host "缓存说明："
Write-Host "  cu126 打包缓存: $(Join-Path $root ".portable-venvs")"
Write-Host "  MinGit 下载缓存: $effectiveMinGitCacheDir"
Write-Host "  视频重建环境: $(Join-Path $root ".video-reconstruction-env")"
Write-Host "  pip 缓存: $env:LOCALAPPDATA\pip\Cache"
Write-Host "  npm 缓存: $env:LOCALAPPDATA\npm-cache"
Write-Host "如需手动清理项目内打包缓存，可运行："
Write-Host "  rmdir /s /q .portable-venvs"
Write-Host "旧版本 ZIP 默认保留在 portable-dist；如需清理，请手动删除不需要的版本。"











