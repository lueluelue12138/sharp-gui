function Get-RequiredObjectPropertyValue {
    param(
        [object]$Object,
        [string]$Name,
        [string]$Context
    )

    if ($null -eq $Object) {
        Fail "update-manifest.json is missing required object: $Context"
    }

    $property = $Object.PSObject.Properties[$Name]
    if (-not $property -or $null -eq $property.Value) {
        Fail "update-manifest.json is missing required field: $Context.$Name"
    }

    return $property.Value
}

function Test-VersionAtLeast {
    param(
        [string]$Actual,
        [string]$Minimum
    )

    if ($Actual -notmatch '^(\d+)\.(\d+)\.(\d+)') {
        return $false
    }
    $actualVersion = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])

    if ($Minimum -notmatch '^(\d+)\.(\d+)\.(\d+)') {
        return $false
    }
    $minimumVersion = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
    return $actualVersion -ge $minimumVersion
}

function Get-SourceRevision {
    param([string]$Root)

    try {
        $raw = & git -C $Root rev-parse --verify HEAD 2>$null
        $exitCode = $LASTEXITCODE
    } catch {
        Fail "Could not resolve the source Git revision: $($_.Exception.Message)"
    }

    $revision = ([string]($raw | Select-Object -First 1)).Trim().ToLowerInvariant()
    if ($exitCode -ne 0 -or $revision -notmatch '^[0-9a-f]{40}$') {
        Fail "Could not resolve the exact source Git SHA."
    }
    return $revision
}

function Get-ReleaseBaseline {
    param(
        [string]$Root,
        [string]$SourceRevision,
        [string]$FallbackVersion
    )

    try {
        $raw = @(& git -C $Root describe --tags --abbrev=0 $SourceRevision 2>$null)
        $exitCode = $LASTEXITCODE
        $tag = ([string]($raw | Select-Object -First 1)).Trim()
        if ($exitCode -eq 0 -and $tag -match '^v\d+\.\d+\.\d+([.-](rc|alpha|beta|preview)\.?\d*)?$') {
            return $tag
        }
    } catch {
    }

    return $FallbackVersion
}

function Get-SourceVersion {
    param(
        [string]$Root,
        [string]$SourceRevision
    )

    $versionSpec = "{0}:version.txt" -f $SourceRevision
    try {
        $raw = @(& git -C $Root show --no-ext-diff --no-textconv $versionSpec 2>$null)
        $exitCode = $LASTEXITCODE
    } catch {
        Fail "Could not read version.txt from the source revision: $($_.Exception.Message)"
    }

    $sourceVersion = ([string]($raw | Select-Object -First 1)).Trim()
    if ($exitCode -ne 0 -or [string]::IsNullOrWhiteSpace($sourceVersion)) {
        Fail "Source revision $SourceRevision does not contain a valid version.txt."
    }
    return ($sourceVersion -replace '^refs/tags/', '')
}

function Get-CommitsAhead {
    param(
        [string]$Root,
        [string]$ReleaseBaseline,
        [string]$SourceRevision
    )

    $range = "{0}..{1}" -f $ReleaseBaseline, $SourceRevision
    try {
        $raw = @(& git -C $Root rev-list --count $range 2>$null)
        $exitCode = $LASTEXITCODE
    } catch {
        return $null
    }

    $value = ([string]($raw | Select-Object -First 1)).Trim()
    if ($exitCode -ne 0 -or $value -notmatch '^\d+$') {
        return $null
    }
    return [int]$value
}

function Assert-SourceRepositoryClean {
    param([string]$Root)

    try {
        $status = @(& git -C $Root status --porcelain=v1 --untracked-files=all)
        $exitCode = $LASTEXITCODE
    } catch {
        Fail "Could not inspect the source repository: $($_.Exception.Message)"
    }

    if ($exitCode -ne 0) {
        Fail "Could not inspect the source repository."
    }
    if ($status.Count -gt 0) {
        Write-Host "The source repository has uncommitted files:" -ForegroundColor Yellow
        $status | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        Fail "Commit or move the changes before a real portable build. -PlanOnly remains available."
    }
}

function Get-UpdateCompatibilityInfo {
    param([string]$Root)

    $manifestPath = Join-Path $Root "update-manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        Fail "update-manifest.json is required for portable update compatibility."
    }
    try {
        $manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Fail "Could not parse update-manifest.json: $($_.Exception.Message)"
    }

    $schemaVersionValue = Get-RequiredObjectPropertyValue -Object $manifest -Name "schemaVersion" -Context "manifest"
    $application = [string](Get-RequiredObjectPropertyValue -Object $manifest -Name "application" -Context "manifest")
    $repositoryNode = Get-RequiredObjectPropertyValue -Object $manifest -Name "repository" -Context "manifest"
    $repository = [string](Get-RequiredObjectPropertyValue -Object $repositoryNode -Name "url" -Context "repository")
    $defaultBranch = [string](Get-RequiredObjectPropertyValue -Object $manifest -Name "defaultBranch" -Context "manifest")
    $protocolRevisionValue = Get-RequiredObjectPropertyValue -Object $manifest -Name "updateProtocolRevision" -Context "manifest"
    $runtimeRevisionValue = Get-RequiredObjectPropertyValue -Object $manifest -Name "portableRuntimeRevision" -Context "manifest"
    $minimumGitVersion = [string](Get-RequiredObjectPropertyValue -Object $manifest -Name "minimumGitVersion" -Context "manifest")
    $frontendNode = Get-RequiredObjectPropertyValue -Object $manifest -Name "frontend" -Context "manifest"
    $builtAssetsRequired = Get-RequiredObjectPropertyValue -Object $frontendNode -Name "builtAssetsRequired" -Context "frontend"
    $frontendEntrypoint = [string](Get-RequiredObjectPropertyValue -Object $frontendNode -Name "entrypoint" -Context "frontend")
    $supportedTargetsValue = Get-RequiredObjectPropertyValue -Object $manifest -Name "supportedPortableTargets" -Context "manifest"

    if ([string]$schemaVersionValue -notmatch '^-?\d+$' -or
        [string]$protocolRevisionValue -notmatch '^-?\d+$' -or
        [string]$runtimeRevisionValue -notmatch '^-?\d+$') {
        Fail "Manifest schema, protocol, and runtime revisions must be integers."
    }

    $supportedTargets = @($supportedTargetsValue) | ForEach-Object { ([string]$_).Trim() }
    $info = [PSCustomObject]@{
        ManifestSource = "update-manifest.json"
        SchemaVersion = [int]$schemaVersionValue
        Application = $application
        Repository = $repository
        DefaultBranch = $defaultBranch
        UpdateProtocolRevision = [int]$protocolRevisionValue
        PortableRuntimeRevision = [int]$runtimeRevisionValue
        MinimumGitVersion = $minimumGitVersion
        BuiltAssetsRequired = [bool]$builtAssetsRequired
        FrontendEntrypoint = $frontendEntrypoint
        SupportedPortableTargets = $supportedTargets
    }

    if ($info.SchemaVersion -ne $script:SupportedManifestSchemaVersion) {
        Fail "Unsupported manifest schemaVersion=$($info.SchemaVersion)."
    }
    if ($info.UpdateProtocolRevision -ne $script:SupportedUpdateProtocolRevision) {
        Fail "Unsupported updateProtocolRevision=$($info.UpdateProtocolRevision)."
    }
    if ($info.PortableRuntimeRevision -lt 1) {
        Fail "portableRuntimeRevision must be a positive integer."
    }
    if ($info.Repository -ne $script:CanonicalRepository) {
        Fail "Manifest repository must be $($script:CanonicalRepository)."
    }
    if ($info.Application -ne "sharp-gui" -or $info.DefaultBranch -ne "main") {
        Fail "Manifest must declare application=sharp-gui and defaultBranch=main."
    }
    if (-not $info.SupportedPortableTargets -or $info.SupportedPortableTargets.Count -eq 0 -or @($info.SupportedPortableTargets | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        Fail "Manifest must declare supportedPortableTargets."
    }
    if ([string]::IsNullOrWhiteSpace($info.MinimumGitVersion)) {
        Fail "Manifest minimumGitVersion cannot be empty."
    }
    if ($builtAssetsRequired -isnot [bool]) {
        Fail "Manifest frontend.builtAssetsRequired must be a boolean."
    }
    if ([string]::IsNullOrWhiteSpace($info.FrontendEntrypoint)) {
        Fail "Manifest frontend.entrypoint cannot be empty."
    }
    if ([System.IO.Path]::IsPathRooted($info.FrontendEntrypoint) -or $info.FrontendEntrypoint.StartsWith("/") -or (($info.FrontendEntrypoint -split '[\\/]') -contains "..")) {
        Fail "Manifest frontend.entrypoint must be a safe relative path."
    }
    if (-not (Test-VersionAtLeast -Actual $script:MinGitVersion -Minimum $info.MinimumGitVersion)) {
        Fail "Bundled MinGit $($script:MinGitVersion) is older than required $($info.MinimumGitVersion)."
    }

    return $info
}
