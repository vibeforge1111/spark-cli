param(
    [string]$Prefix = "$HOME\.spark",
    [string]$Source = "https://github.com/vibeforge1111/spark-cli",
    [string]$Ref = "spark-cli-public-installer-2026-06-03-r24-v2",
    [string]$NodeVersion = "22.18.0",
    [string]$PythonVersion = "3.11",
    [string]$UvVersion = "0.11.7",
    [string]$Bundle = "telegram-starter",
    [string]$BotToken = "",
    [string]$AdminTelegramIds = "",
    [string]$LlmProvider = "",
    [string]$ZaiApiKey = "",
    [string]$OpenAIApiKey = "",
    [string]$AnthropicApiKey = "",
    [string]$MiniMaxApiKey = "",
    [switch]$NonInteractiveSetup,
    [switch]$SetupSkipInstallCommands,
    [switch]$SetupSkipRuntimeCheck,
    [switch]$ManagedNode,
    [string[]]$SetupArg = @(),
    [string]$LocalRegistry = "",
    [switch]$SkipSetup,
    [switch]$Autostart,
    [switch]$NoAutostart,
    [switch]$AllowDevSource,
    [switch]$DryRun,
    [switch]$Preflight,
    [switch]$Yes,
    [switch]$UpgradeExisting
)

$ErrorActionPreference = "Stop"
$SparkCliReleaseName = "spark-cli-public-installer-2026-06-03-r24-v2"
$RefWasProvided = $PSBoundParameters.ContainsKey("Ref")
$Script:InstallLockDir = ""
$Script:PythonExe = ""
$Script:UvExe = ""
$Script:InstallLogPath = ""
$Script:TranscriptStarted = $false
$Script:AutostartAutoDisabled = $false
$Script:AutostartWasProvided = $PSBoundParameters.ContainsKey("Autostart") -or $PSBoundParameters.ContainsKey("NoAutostart")

function Write-SparkLog {
    param([string]$Message)
    Write-Host "[spark-install] $Message"
}

function Apply-InstallDefaults {
    if ($Autostart) {
        $script:NoAutostart = $false
        return
    }
    if (-not $Script:AutostartWasProvided -and ($Yes -or [Console]::IsInputRedirected)) {
        $script:NoAutostart = $true
        $Script:AutostartAutoDisabled = $true
    }
    if ($Yes -or [Console]::IsInputRedirected) {
        $script:NonInteractiveSetup = $true
    }
}

function Test-BundleIncludesVoice {
    return $Bundle -like "*voice*"
}

function Format-AutostartPlan {
    if (-not $NoAutostart) {
        return "yes; will mutate login items"
    }
    if ($Script:AutostartAutoDisabled) {
        return "no; auto-disabled for -Yes/non-interactive run"
    }
    return "no"
}

function Format-InstallerRunMode {
    if ($Yes) {
        return "unattended (-Yes)"
    }
    if ([Console]::IsInputRedirected) {
        return "unattended (non-interactive stdin)"
    }
    return "interactive"
}

function Resolve-FullPath {
    param([string]$Path)
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [System.IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path (Get-Location) $expanded
    }
    return [System.IO.Path]::GetFullPath($expanded)
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Test-PythonCompatible {
    param([string]$PythonExe)
    & $PythonExe -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)' 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

function Find-SystemPython {
    foreach ($name in @("python3.11", "python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and (Test-PythonCompatible $cmd.Source)) {
            $Script:PythonExe = $cmd.Source
            return $true
        }
    }
    return $false
}

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) {
        $uvDir = Split-Path -Parent $cmd.Source
        if ((Test-Path -LiteralPath (Join-Path $uvDir "uvx.exe")) -or (Get-Command uvx -ErrorAction SilentlyContinue)) {
            $Script:UvExe = $cmd.Source
            return $true
        }
    }
    foreach ($candidate in @(
        (Join-Path $HOME ".local\bin\uv.exe"),
        (Join-Path $HOME ".cargo\bin\uv.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) {
            $uvDir = Split-Path -Parent $candidate
            if ((Test-Path -LiteralPath (Join-Path $uvDir "uvx.exe")) -or (Get-Command uvx -ErrorAction SilentlyContinue)) {
                $Script:UvExe = $candidate
                return $true
            }
        }
    }
    return $false
}

function Get-UvPlatform {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($arch -eq "ARM64") {
        return "aarch64-pc-windows-msvc"
    }
    if ($arch -eq "AMD64" -or $arch -eq "x86_64") {
        return "x86_64-pc-windows-msvc"
    }
    throw "Unsupported Windows architecture for uv: $arch"
}

function Get-UvAssetSha256 {
    param([string]$Asset)
    switch ($Asset) {
        "uv-aarch64-pc-windows-msvc.zip" { return "1387e1c94e15196351196b79fce4c1e6f4b30f19cdaaf9ff85fbd6b046018aa2" }
        "uv-x86_64-pc-windows-msvc.zip" { return "fe0c7815acf4fc45f8a5eff58ed3cf7ae2e15c3cf1dceadbd10c816ec1690cc1" }
        default { throw "No pinned uv checksum for asset: $Asset" }
    }
}

function Install-Uv {
    if (Find-Uv) {
        Write-SparkLog "Using uv at $Script:UvExe"
        return
    }
    $uvPlatform = Get-UvPlatform
    $asset = "uv-$uvPlatform.zip"
    $expected = Get-UvAssetSha256 $asset
    $toolsDir = Join-Path $Script:SparkPrefix "tools"
    $uvDir = Join-Path $toolsDir "uv-v$UvVersion-$uvPlatform"
    $archive = Join-Path $toolsDir $asset
    $extractDir = Join-Path $toolsDir "uv-extract-$UvVersion-$uvPlatform"
    $uvExe = Join-Path $uvDir "uv.exe"
    $uvxExe = Join-Path $uvDir "uvx.exe"
    if ((Test-Path -LiteralPath $uvExe) -and (Test-Path -LiteralPath $uvxExe)) {
        $Script:UvExe = $uvExe
        Write-SparkLog "Using managed uv at $Script:UvExe"
        return
    }
    if (Test-Path -LiteralPath $uvExe) {
        Write-SparkLog "Refreshing managed uv because uvx.exe is missing"
        Remove-Item -LiteralPath $uvExe -Force
        Remove-Item -LiteralPath $uvxExe -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Force -Path $toolsDir, $uvDir | Out-Null
    Write-SparkLog "Downloading pinned uv $UvVersion for $uvPlatform"
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/$asset" -OutFile $archive
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "uv archive checksum mismatch for $asset"
    }
    if (Test-Path -LiteralPath $extractDir) {
        Remove-Item -LiteralPath $extractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
    Expand-Archive -Path $archive -DestinationPath $extractDir -Force
    $extractedUv = Get-ChildItem -LiteralPath $extractDir -Filter uv.exe -Recurse | Select-Object -First 1
    if (-not $extractedUv) {
        throw "uv archive did not contain uv.exe"
    }
    Copy-Item -LiteralPath $extractedUv.FullName -Destination $uvExe -Force
    $extractedUvx = Get-ChildItem -LiteralPath $extractDir -Filter uvx.exe -Recurse | Select-Object -First 1
    if ($extractedUvx) {
        Copy-Item -LiteralPath $extractedUvx.FullName -Destination (Join-Path $uvDir "uvx.exe") -Force
    }
    Remove-Item -LiteralPath $extractDir -Recurse -Force
    $Script:UvExe = $uvExe
    Write-SparkLog "Using managed uv at $Script:UvExe"
}

function Ensure-UvxForBrowserUse {
    Install-Uv
    $uvDir = Split-Path -Parent $Script:UvExe
    $uvxExe = Join-Path $uvDir "uvx.exe"
    if (Test-Path -LiteralPath $uvxExe) {
        return $uvDir
    }
    $uvxOnPath = Get-Command uvx -ErrorAction SilentlyContinue
    if ($uvxOnPath) {
        return (Split-Path -Parent $uvxOnPath.Source)
    }
    $managedRoot = Join-Path $Script:SparkPrefix "tools"
    if ($Script:UvExe -and $Script:UvExe.StartsWith($managedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Managed uv at $Script:UvExe did not provide a paired uvx.exe, which browser-use needs to install Chromium. Remove $uvDir and re-run install.ps1 to refresh the bundled uv."
    }
    throw "Found uv at $Script:UvExe but no paired uvx.exe, and uvx is not on PATH. browser-use needs uvx to install Chromium. Install uv with its bundled uvx, or remove the existing uv so install.ps1 can fetch the bundled copy."
}

function Ensure-PythonRuntime {
    if (Find-SystemPython) {
        $versionText = (& $Script:PythonExe --version 2>$null)
        Write-SparkLog "Using Python runtime: $versionText at $Script:PythonExe"
        return
    }
    Install-Uv
    Write-SparkLog "Installing Python $PythonVersion via uv"
    & $Script:UvExe python install $PythonVersion | Out-Null
    $Script:PythonExe = (& $Script:UvExe python find $PythonVersion)
    if (-not $Script:PythonExe -or -not (Test-PythonCompatible $Script:PythonExe)) {
        throw "Could not resolve managed Python $PythonVersion via uv."
    }
    $managedVersion = (& $Script:PythonExe --version 2>$null)
    Write-SparkLog "Using managed Python runtime: $managedVersion at $Script:PythonExe"
}

function Test-ExistingInstall {
    return (
        (Test-Path (Join-Path $Script:SparkPrefix "bin\spark.cmd")) -or
        (Test-Path (Join-Path $Script:SparkPrefix "tools\spark-cli")) -or
        (Test-Path (Join-Path $Script:SparkPrefix "config")) -or
        (Test-Path (Join-Path $Script:SparkPrefix "state"))
    )
}

function Invoke-Preflight {
    Write-SparkLog "Preflight checks"
    if (Find-SystemPython) {
        $versionText = (& $Script:PythonExe --version 2>$null)
        Write-SparkLog "Python runtime: $versionText at $Script:PythonExe"
    } else {
        Write-SparkLog "Python runtime: Python >=3.11,<3.14 not found; pinned uv $UvVersion will be downloaded after confirmation"
    }
    Require-Command git
    Write-SparkLog "Install prefix: $Script:SparkPrefix"
    Write-SparkLog "Spark CLI source: $Source"
    Write-SparkLog "Spark CLI ref: $Ref"
    Write-SparkLog "Node version: $NodeVersion"
    Write-SparkLog "Python version: $PythonVersion"
    Write-SparkLog "Bundle: $Bundle"
    Write-SparkLog "Autostart: $(Format-AutostartPlan)"
    if (Test-ExistingInstall) {
        Write-SparkLog "Existing Spark install detected at $Script:SparkPrefix"
    } else {
        Write-SparkLog "No existing Spark install detected at $Script:SparkPrefix"
    }
}

function Test-ExistingInstallPolicy {
    if (-not (Test-ExistingInstall)) {
        return
    }
    if ($UpgradeExisting) {
        Write-SparkLog "Existing install update explicitly allowed by -UpgradeExisting"
        return
    }
    throw @"
Existing Spark install detected at:
  $Script:SparkPrefix

This installer will not overwrite or update an existing install by default.
Choose one:
  - use -UpgradeExisting after reviewing local changes and backups
  - use -Prefix "$env:TEMP\spark-install-test" for a disposable test install
  - run the existing Spark repair tools instead of reinstalling
"@
}

function Show-DryRunPlan {
    $setupEnabled = if ($SkipSetup) { "no" } else { "yes" }
    $autostartEnabled = Format-AutostartPlan
    $voiceIncluded = if (Test-BundleIncludesVoice) { "yes" } else { "no" }
    $existing = if (Test-ExistingInstall) { "detected" } else { "none" }
    $existingMode = if ($UpgradeExisting) { "upgrade" } else { "abort" }
    Write-Host "Spark install preview"
    Write-Host "Nothing has changed yet."
    Write-Host ""
    Write-Host "Spark will:"
    Write-Host "  1. Install the Spark command"
    Write-Host "  2. Help you choose how Spark thinks"
    Write-Host "  3. Connect your Telegram bot"
    Write-Host "  4. Start Spark so you can chat and build"
    Write-Host ""
    Write-Host "Details:"
    Write-Host "  Dry-run safety:     no network and no writes in -DryRun mode"
    Write-Host "  Prefix:              $Script:SparkPrefix"
    Write-Host "  Node platform:       win-x64"
    Write-Host "  Node version:        $NodeVersion"
    Write-Host "  Python version:      $PythonVersion"
    Write-Host "  Python source:       existing Python >=3.11,<3.14 or pinned uv $UvVersion if needed"
    Write-Host "  Managed Node forced: $ManagedNode"
    Write-Host "  CLI source:          $Source"
    Write-Host "  CLI release:         $SparkCliReleaseName"
    Write-Host "  CLI commit:          $Ref"
    Write-Host "  Bundle:              $Bundle"
    Write-Host "  Voice included:      $voiceIncluded"
    Write-Host "  Run mode:            $(Format-InstallerRunMode)"
    Write-Host "  Setup enabled:       $setupEnabled"
    $providerPlan = if ($LlmProvider) { "$LlmProvider for Agent and Mission" } else { "choose during spark setup" }
    Write-Host "  Default provider:    $providerPlan"
    Write-Host "  User PATH edit:      yes"
    Write-Host "  Autostart:           $autostartEnabled"
    Write-Host "  Existing mode:       $existingMode"
    Write-Host "  Existing install:    $existing"
    Write-Host "  Install log:         $Script:SparkPrefix\logs\install.log"
    Write-Host ""
    Write-Host "Would write:"
    Write-Host "  $Script:SparkPrefix\tools"
    Write-Host "  $Script:SparkPrefix\tools\spark-cli"
    Write-Host "  $Script:SparkPrefix\tools\spark-cli-venv"
    Write-Host "  $Script:SparkPrefix\bin\spark.cmd"
    Write-Host ""
    Write-Host "Would download if needed:"
    Write-Host "  Node $NodeVersion from nodejs.org"
    Write-Host "  uv $UvVersion from github.com/astral-sh/uv when Python >=3.11,<3.14 is missing"
    Write-Host "  Python $PythonVersion via uv when Python >=3.11,<3.14 is missing"
    Write-Host "  Spark CLI from $Source at $Ref"
    Write-Host ""
    Write-Host "Expected installer network access:"
    Write-Host "  nodejs.org"
    Write-Host "  github.com/astral-sh/uv"
    Write-Host "  github.com/vibeforge1111/spark-cli"
    Write-Host ""
    Write-Host "Would run:"
    Write-Host "  python -m venv `"$Script:SparkPrefix\tools\spark-cli-venv`""
    if (-not $SkipSetup) {
        function Format-SetupPreviewArg {
            param([string]$Value)
            if ($Value -match '[\s"]') {
                return '"' + $Value.Replace('"', '\"') + '"'
            }
            return $Value
        }
        $setupPreviewArgs = @()
        $setupPreviewArgs += if ($NoAutostart) { @("--no-start-now", "--no-autostart") } else { @("--start-now", "--autostart") }
        if ($NonInteractiveSetup) { $setupPreviewArgs += "--non-interactive" }
        if ($SetupSkipInstallCommands) { $setupPreviewArgs += "--skip-install-commands" }
        if ($SetupSkipRuntimeCheck) { $setupPreviewArgs += "--skip-runtime-check" }
        if ($BotToken) { $setupPreviewArgs += @("--bot-token", "<redacted>") }
        if ($AdminTelegramIds) { $setupPreviewArgs += @("--admin-telegram-ids", "<redacted>") }
        if ($LlmProvider) { $setupPreviewArgs += @("--llm-provider", $LlmProvider) }
        if ($ZaiApiKey) { $setupPreviewArgs += @("--zai-api-key", "<redacted>") }
        if ($OpenAIApiKey) { $setupPreviewArgs += @("--openai-api-key", "<redacted>") }
        if ($AnthropicApiKey) { $setupPreviewArgs += @("--anthropic-api-key", "<redacted>") }
        if ($MiniMaxApiKey) { $setupPreviewArgs += @("--minimax-api-key", "<redacted>") }
        $setupPreviewArgs += $SetupArg
        $setupPreview = ($setupPreviewArgs | ForEach-Object { Format-SetupPreviewArg $_ }) -join " "
        Write-Host "  `"$Script:SparkPrefix\bin\spark.cmd`" setup `"$Bundle`" $setupPreview"
    }
}

function Confirm-Install {
    if ($Yes) {
        return $true
    }
    try {
        $answer = Read-Host "Ready to install Spark now? Type yes to continue, or press Ctrl-C to cancel"
    } catch {
        throw "Interactive confirmation is required before installing. Rerun with -Yes only after reviewing the dry-run plan."
    }
    if ($answer -eq "yes") {
        return $true
    }
    Write-Host "Skipped."
    return $false
}

function Acquire-InstallLock {
    $Script:InstallLockDir = Join-Path $Script:SparkPrefix ".install.lock"
    try {
        New-Item -ItemType Directory -Path $Script:InstallLockDir -ErrorAction Stop | Out-Null
    } catch {
        throw "Another Spark install appears to be running: $Script:InstallLockDir. If this is stale, remove it after confirming no installer is active."
    }
}

function Release-InstallLock {
    if ($Script:InstallLockDir -and (Test-Path $Script:InstallLockDir)) {
        Remove-Item -LiteralPath $Script:InstallLockDir -Force -ErrorAction SilentlyContinue
        $Script:InstallLockDir = ""
    }
}

function Start-InstallLog {
    $logDir = Join-Path $Script:SparkPrefix "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $Script:InstallLogPath = Join-Path $logDir "install.log"
    Write-SparkLog "Writing install log to $Script:InstallLogPath"
    $transcriptCommand = Get-Command Start-Transcript -ErrorAction SilentlyContinue
    if (-not $transcriptCommand -or -not $transcriptCommand.Parameters.ContainsKey("UseMinimalHeader")) {
        Write-Warning "Install transcript disabled because this PowerShell cannot omit the command-line header."
        return
    }
    try {
        Start-Transcript -Path $Script:InstallLogPath -Append -UseMinimalHeader | Out-Null
        $Script:TranscriptStarted = $true
    } catch {
        Write-Warning "Could not start install transcript at $Script:InstallLogPath"
    }
}

function Stop-InstallLog {
    if ($Script:TranscriptStarted) {
        Stop-Transcript | Out-Null
        $Script:TranscriptStarted = $false
    }
}

function Get-MajorVersion {
    param([string]$VersionText)
    if ($VersionText -match '(\d+)') {
        return [int]$Matches[1]
    }
    return $null
}

function Test-InstallSettings {
    $canonicalSource = "https://github.com/vibeforge1111/spark-cli"
    if ([string]::IsNullOrWhiteSpace($Script:SparkPrefix)) {
        throw "Refusing empty install prefix"
    }
    $root = [System.IO.Path]::GetPathRoot($Script:SparkPrefix)
    if ($Script:SparkPrefix.TrimEnd('\') -eq $root.TrimEnd('\')) {
        throw "Refusing unsafe install prefix: $Script:SparkPrefix"
    }
    if ($NodeVersion -notmatch '^\d+\.\d+\.\d+$') {
        throw "Unsafe Node version value: $NodeVersion"
    }
    if ($PythonVersion -notmatch '^\d+\.\d+(\.\d+)?$') {
        throw "Unsafe Python version value: $PythonVersion"
    }
    if ($UvVersion -notmatch '^\d+\.\d+\.\d+$') {
        throw "Unsafe uv version value: $UvVersion"
    }
    if (-not $RefWasProvided -and $Ref -notmatch '^([0-9a-f]{40}|spark-cli-public-installer-\d{4}-\d{2}-\d{2}-r\d+(-v\d+)?)$') {
        throw "Default Spark CLI ref must be a 40-character commit SHA or Spark public release tag: $Ref"
    }
    $normalizedSource = $Source.TrimEnd("/")
    if ($normalizedSource.EndsWith(".git")) {
        $normalizedSource = $normalizedSource.Substring(0, $normalizedSource.Length - 4)
    }
    if ($normalizedSource -ne $canonicalSource -and -not $AllowDevSource) {
        throw "Refusing non-canonical Spark CLI source: $Source. Use -AllowDevSource only for local development after reviewing the source."
    }
    if ($RefWasProvided -and $Ref -and -not $AllowDevSource) {
        throw "Refusing custom git ref without -AllowDevSource: $Ref"
    }
    if ($LocalRegistry -and -not $AllowDevSource) {
        throw "Refusing local registry override without -AllowDevSource: $LocalRegistry"
    }
}

function Find-SystemNodeDir {
    if ($ManagedNode) {
        return $null
    }
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $nodeCommand -or -not $npmCommand) {
        return $null
    }
    $requiredMajor = Get-MajorVersion $NodeVersion
    $actualVersion = (& $nodeCommand.Source -v 2>$null)
    $actualMajor = Get-MajorVersion $actualVersion
    if ($null -eq $requiredMajor -or $null -eq $actualMajor -or $actualMajor -lt $requiredMajor) {
        return $null
    }
    $nodeDir = Split-Path -Parent $nodeCommand.Source
    Write-SparkLog "Using system Node $actualVersion at $nodeDir"
    Write-SparkLog "Use -ManagedNode to force Spark's verified managed Node download."
    return $nodeDir
}

function Install-Node {
    $systemNodeDir = Find-SystemNodeDir
    if ($systemNodeDir) {
        return $systemNodeDir
    }

    $toolsDir = Join-Path $Script:SparkPrefix "tools"
    $nodeDir = Join-Path $toolsDir "node-v$NodeVersion-win-x64"
    $nodeExe = Join-Path $nodeDir "node.exe"
    if (Test-Path $nodeExe) {
        Write-SparkLog "Node $NodeVersion already installed at $nodeDir"
        return $nodeDir
    }

    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    $archive = Join-Path $toolsDir "node-v$NodeVersion-win-x64.zip"
    $shasums = Join-Path $toolsDir "node-v$NodeVersion-SHASUMS256.txt"
    $url = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
    $shasumsUrl = "https://nodejs.org/dist/v$NodeVersion/SHASUMS256.txt"
    Write-SparkLog "Downloading Node $NodeVersion"
    Invoke-WebRequest -Uri $url -OutFile $archive
    Invoke-WebRequest -Uri $shasumsUrl -OutFile $shasums
    Test-NodeArchiveHash -Archive $archive -Shasums $shasums
    Write-SparkLog "Extracting Node $NodeVersion"
    Expand-Archive -Path $archive -DestinationPath $toolsDir -Force
    return $nodeDir
}

function Test-NodeArchiveHash {
    param([string]$Archive, [string]$Shasums)
    $archiveName = Split-Path $Archive -Leaf
    $line = Get-Content -LiteralPath $Shasums | Where-Object { $_ -match "^\S+\s+$([regex]::Escape($archiveName))$" } | Select-Object -First 1
    if (-not $line) {
        throw "Could not find $archiveName in Node SHASUMS256.txt"
    }
    $expected = ($line -split "\s+")[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "Node archive checksum mismatch for $archiveName"
    }
}

function Copy-DirectoryContents {
    param([string]$From, [string]$To)
    if (Test-Path $To) {
        Remove-Item -LiteralPath $To -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    Get-ChildItem -LiteralPath $From -Force |
        Where-Object { $_.Name -notin @(".git", ".venv", ".pytest_cache", "__pycache__") } |
        Copy-Item -Destination $To -Recurse -Force
}

function Invoke-GitQuiet {
    param([string[]]$Arguments)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & git @Arguments 2>&1 | Out-Null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Checkout-CliRef {
    param([string]$Target)
    if ((Invoke-GitQuiet @("-C", $Target, "checkout", $Ref)) -eq 0) {
        return
    }
    if ((Invoke-GitQuiet @("-C", $Target, "fetch", "--depth=1", "origin", $Ref)) -eq 0) {
        if ((Invoke-GitQuiet @("-C", $Target, "checkout", "FETCH_HEAD")) -eq 0) {
            return
        }
    }
    if ($Ref -match "^[0-9a-f]{40}$") {
        $isShallow = (& git -C $Target rev-parse --is-shallow-repository 2>$null)
        if ($isShallow -eq "true") {
            git -C $Target fetch --unshallow origin
        } else {
            git -C $Target fetch origin
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Could not fetch Spark CLI history for commit ref: $Ref"
        }
        git -C $Target checkout $Ref
        if ($LASTEXITCODE -ne 0) {
            throw "Could not checkout Spark CLI commit ref: $Ref"
        }
        return
    }
    git -C $Target fetch --depth=1 origin "refs/tags/${Ref}:refs/tags/${Ref}"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not fetch Spark CLI ref: $Ref"
    }
    git -C $Target checkout $Ref
    if ($LASTEXITCODE -ne 0) {
        throw "Could not checkout Spark CLI ref: $Ref"
    }
}

function Checkout-Cli {
    $target = Join-Path $Script:SparkPrefix "tools\spark-cli"
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    if (Test-Path $Source) {
        Write-SparkLog "Copying spark-cli from local path $Source"
        Copy-DirectoryContents -From (Resolve-FullPath $Source) -To $target
        return $target
    }

    Require-Command git
    if (Test-Path (Join-Path $target ".git")) {
        Write-SparkLog "Updating existing spark-cli checkout"
    } else {
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
        Write-SparkLog "Cloning spark-cli from $Source"
        if ($Ref -match "^[0-9a-f]{40}$") {
            git clone $Source $target
        } else {
            git clone --depth=1 $Source $target
        }
    }
    Checkout-CliRef -Target $target
    return $target
}

function Install-CliVenv {
    param([string]$CliDir)
    $venvDir = Join-Path $Script:SparkPrefix "tools\spark-cli-venv"
    $uvDir = Ensure-UvxForBrowserUse
    Write-SparkLog "Creating Spark CLI virtualenv"
    & $Script:PythonExe -m venv $venvDir
    Write-SparkLog "Upgrading pip in Spark CLI virtualenv"
    & (Join-Path $venvDir "Scripts\python.exe") -m pip install --upgrade pip | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in Spark CLI virtualenv." }
    Write-SparkLog "Installing Spark CLI package with browser-use support"
    & (Join-Path $venvDir "Scripts\python.exe") -m pip install -e "$CliDir[browser-use]" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Spark CLI package with browser-use support." }
    Write-SparkLog "Installing browser-use Chromium dependency"
    $oldPath = $env:PATH
    $oldPythonIoEncoding = $env:PYTHONIOENCODING
    $oldPythonUtf8 = $env:PYTHONUTF8
    try {
        $env:PATH = "$(Join-Path $venvDir "Scripts");$uvDir;$env:PATH"
        $env:PYTHONIOENCODING = "utf-8"
        $env:PYTHONUTF8 = "1"
        & (Join-Path $venvDir "Scripts\browser-use.exe") install | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to install browser-use Chromium dependency." }
    } finally {
        $env:PATH = $oldPath
        $env:PYTHONIOENCODING = $oldPythonIoEncoding
        $env:PYTHONUTF8 = $oldPythonUtf8
    }
    return $venvDir
}

function Write-Wrapper {
    param([string]$NodeDir, [string]$VenvDir)
    $binDir = Join-Path $Script:SparkPrefix "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $wrapper = Join-Path $binDir "spark.cmd"
    $legacyExe = Join-Path $binDir "spark.exe"
    if (Test-Path -LiteralPath $legacyExe) {
        Remove-Item -LiteralPath $legacyExe -Force
        Write-SparkLog "Removed stale Spark executable shim $legacyExe"
    }
    $pythonExe = Join-Path $VenvDir "Scripts\python.exe"
    $contents = @"
@echo off
set "SPARK_HOME=$Script:SparkPrefix"
set "PATH=$NodeDir;%PATH%"
"$pythonExe" -m spark_cli.cli %*
"@
    Set-Content -Path $wrapper -Value $contents -Encoding ASCII
    Write-SparkLog "Wrote wrapper $wrapper"
}

function Add-SparkBinToUserPath {
    $binDir = Join-Path $Script:SparkPrefix "bin"
    $tempRoot = Resolve-FullPath $env:TEMP
    if ($Script:SparkPrefix.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        $env:PATH = "$binDir;$env:PATH"
        Write-SparkLog "Skipping persistent PATH update for temporary install prefix $Script:SparkPrefix"
        return
    }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($userPath -split ";" | Where-Object { $_ -and $_.Trim() })
    $alreadyPresent = $parts | Where-Object { $_.TrimEnd("\") -ieq $binDir.TrimEnd("\") } | Select-Object -First 1
    if (-not $alreadyPresent) {
        $newPath = (($binDir) + ";" + ($parts -join ";")).TrimEnd(";")
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:PATH = "$binDir;$env:PATH"
        Write-SparkLog "Added $binDir to your user PATH"
        Write-SparkLog "Open a new terminal before running `spark` by name."
    } else {
        $env:PATH = "$binDir;$env:PATH"
        Write-SparkLog "$binDir is already on your user PATH"
    }
}

function Warn-SparkCommandConflict {
    $expected = (Join-Path $Script:SparkPrefix "bin\spark.cmd").TrimEnd("\")
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $pathEntries = @($machinePath -split ";" | Where-Object { $_ -and $_.Trim() })
    $pathEntries += @($userPath -split ";" | Where-Object { $_ -and $_.Trim() })
    foreach ($entry in $pathEntries) {
        $expanded = [Environment]::ExpandEnvironmentVariables($entry)
        foreach ($name in @("spark.exe", "spark.cmd", "spark.bat")) {
            $candidate = Join-Path $expanded $name
            if (Test-Path -LiteralPath $candidate) {
                if ($candidate.TrimEnd("\") -ine $expected) {
                    Write-Warning "A different spark command is earlier on fresh Windows PATH: $candidate"
                    Write-Host "Use this Spark wrapper until that old command is removed or PATH is reordered:"
                    Write-Host "  $expected"
                }
                return
            }
        }
    }
}

function Run-Setup {
    param([string]$CliDir)
    if ($SkipSetup) {
        Write-SparkLog "Skipping spark setup"
        return
    }
    if ($LocalRegistry) {
        Write-SparkLog "Using registry override $LocalRegistry"
        Copy-Item -LiteralPath $LocalRegistry -Destination (Join-Path $CliDir "registry.json") -Force
    }
    $sparkCmd = Join-Path $Script:SparkPrefix "bin\spark.cmd"
    $secretFiles = [System.Collections.Generic.List[string]]::new()
    function New-SetupSecretRef {
        param([string]$Value)
        $secretFile = [System.IO.Path]::GetTempFileName()
        [System.IO.File]::WriteAllText($secretFile, $Value, [System.Text.UTF8Encoding]::new($false))
        [void]$secretFiles.Add($secretFile)
        return "@file:$secretFile"
    }
    $setupArgs = @()
    if ($NonInteractiveSetup) { $setupArgs += "--non-interactive" }
    if ($SetupSkipInstallCommands) { $setupArgs += "--skip-install-commands" }
    if ($SetupSkipRuntimeCheck) { $setupArgs += "--skip-runtime-check" }
    if ($BotToken) { $setupArgs += @("--bot-token", (New-SetupSecretRef $BotToken)) }
    if ($AdminTelegramIds) { $setupArgs += @("--admin-telegram-ids", $AdminTelegramIds) }
    if ($LlmProvider) { $setupArgs += @("--llm-provider", $LlmProvider) }
    if ($ZaiApiKey) { $setupArgs += @("--zai-api-key", (New-SetupSecretRef $ZaiApiKey)) }
    if ($OpenAIApiKey) { $setupArgs += @("--openai-api-key", (New-SetupSecretRef $OpenAIApiKey)) }
    if ($AnthropicApiKey) { $setupArgs += @("--anthropic-api-key", (New-SetupSecretRef $AnthropicApiKey)) }
    if ($MiniMaxApiKey) { $setupArgs += @("--minimax-api-key", (New-SetupSecretRef $MiniMaxApiKey)) }
    $setupArgs += $SetupArg
    Write-SparkLog "Running spark setup $Bundle"
    $previousSetupOptional = $env:SPARK_SETUP_OPTIONAL_ON_UPGRADE
    try {
        if ($UpgradeExisting) {
            $env:SPARK_SETUP_OPTIONAL_ON_UPGRADE = "1"
        }
        $setupStartArgs = if ($NoAutostart) { @("--no-start-now", "--no-autostart") } else { @("--start-now", "--autostart") }
        & $sparkCmd setup $Bundle @setupStartArgs @setupArgs
        if ($LASTEXITCODE -ne 0) {
            throw "spark setup failed with exit code $LASTEXITCODE"
        }
    } finally {
        if ($null -eq $previousSetupOptional) {
            Remove-Item Env:\SPARK_SETUP_OPTIONAL_ON_UPGRADE -ErrorAction SilentlyContinue
        } else {
            $env:SPARK_SETUP_OPTIONAL_ON_UPGRADE = $previousSetupOptional
        }
        foreach ($secretFile in $secretFiles) {
            Remove-Item -LiteralPath $secretFile -Force -ErrorAction SilentlyContinue
        }
    }
}

function Run-Autostart {
    if ($SkipSetup) {
        return
    }
    Write-SparkLog "Spark startup was handled by setup"
}

function Test-SetupRefreshPaused {
    $pendingSetupPath = Join-Path $Script:SparkPrefix "state\setup.pending.json"
    if (-not (Test-Path -LiteralPath $pendingSetupPath)) {
        return $false
    }
    try {
        return (Get-Content -LiteralPath $pendingSetupPath -Raw -ErrorAction Stop).Contains('"event": "setup_refresh_paused"')
    } catch {
        return $false
    }
}

function Show-InstallOutcome {
    $pendingSetupPath = Join-Path $Script:SparkPrefix "state\setup.pending.json"
    if ($SkipSetup) {
        $setupLine = "[SKIP] Setup: skipped by request"
        $runtimeLine = "[MANUAL] Runtime: start after setup"
        $telegramLine = "[VERIFY] Telegram: run spark verify --onboarding after setup"
    } elseif (Test-SetupRefreshPaused) {
        $setupLine = "[PAUSED] Setup refresh: secrets need a secure backend before Spark rewrites them"
        $runtimeLine = "[OK] Existing runtime: can keep running with the current setup"
        $telegramLine = "[VERIFY] Telegram: run spark verify --onboarding"
    } elseif (Test-Path -LiteralPath $pendingSetupPath) {
        $setupLine = "[PAUSED] Setup: run spark doctor"
        $runtimeLine = "[MANUAL] Runtime: resume setup before changing secrets"
        $telegramLine = "[VERIFY] Telegram: run spark verify --onboarding after setup resumes"
    } else {
        $setupLine = "[OK] Setup: configured"
        if ($NoAutostart) {
            $runtimeLine = "[MANUAL] Runtime: start after setup"
        } else {
            $runtimeLine = "[STARTED] Runtime: setup handled start/autostart"
        }
        $telegramLine = "[VERIFY] Telegram: run spark verify --onboarding"
    }
    Write-Host ""
    Write-Host "Install outcome:"
    Write-Host "  [OK] CLI upgrade: complete"
    Write-Host "  $setupLine"
    Write-Host "  $runtimeLine"
    Write-Host "  $telegramLine"
}

function Invoke-Install {
    $Script:SparkPrefix = Resolve-FullPath $Prefix
    Apply-InstallDefaults
    Test-InstallSettings
    if ($DryRun) {
        Show-DryRunPlan
        return
    }
    Show-DryRunPlan
    Invoke-Preflight
    if ($Preflight) {
        Write-SparkLog "Preflight complete."
        return
    }
    Test-ExistingInstallPolicy
    if (-not (Confirm-Install)) {
        return
    }
    New-Item -ItemType Directory -Force -Path $Script:SparkPrefix | Out-Null
    Ensure-PythonRuntime
    Start-InstallLog
    Acquire-InstallLock
    $nodeDir = Install-Node
    $env:PATH = "$nodeDir;$env:PATH"
    Write-SparkLog "Node runtime: $(& (Join-Path $nodeDir "node.exe") -v)"
    $cliDir = Checkout-Cli
    $venvDir = Install-CliVenv -CliDir $cliDir
    Write-Wrapper -NodeDir $nodeDir -VenvDir $venvDir
    Add-SparkBinToUserPath
    Warn-SparkCommandConflict
    Run-Setup -CliDir $cliDir
    Run-Autostart
    Write-SparkLog "Done."
    Write-Host ""
    Write-Host "Spark command:"
    Write-Host "  spark --help"
    Write-Host "  spark guide"
    Write-Host "  spark providers list"
    Write-Host ""
    Write-Host "Direct wrapper path:"
    Write-Host "  $Script:SparkPrefix\bin\spark.cmd --help"
    Write-Host "  $Script:SparkPrefix\bin\spark.cmd guide"
    Write-Host "  $Script:SparkPrefix\bin\spark.cmd providers list"
    Write-Host ""
    Write-Host "If `spark` is not found in this terminal yet, close and reopen the terminal."
    Write-Host ""
    Write-Host "Install log:"
    Write-Host "  $Script:InstallLogPath"
    Show-InstallOutcome
    Write-Host ""
    if ($SkipSetup) {
        Write-Host "Setup was skipped."
        Write-Host "Next:"
        Write-Host "  $Script:SparkPrefix\bin\spark.cmd setup $Bundle"
        Write-Host ""
        Write-Host "After setup succeeds:"
        Write-Host "  $Script:SparkPrefix\bin\spark.cmd verify --onboarding"
        return
    }
    Write-Host ""
    Write-Host "Operational checks:"
    Write-Host "  spark live start"
    Write-Host "  spark live status"
    Write-Host "  spark providers status"
    Write-Host "  spark providers test --role chat"
    Write-Host "  spark verify --onboarding"
    Write-Host "  spark autostart status"
    Write-Host "  spark fix autostart"
    Write-Host ""
    if ($NoAutostart) {
        Write-Host "Autostart was not installed for this run."
        Write-Host "To enable it later:"
        Write-Host "  spark autostart on telegram-starter --now"
    } else {
        Write-Host "Spark autostart is enabled by default so Spark comes back after login."
        Write-Host "To disable it later:"
        Write-Host "  spark autostart off"
    }
    Write-Host ""
    Write-Host "Start chatting and building:"
    Write-Host "  1. Open your Spark bot in Telegram"
    Write-Host "  2. If Telegram asks for a start code, send /start"
    Write-Host "  3. For first builds, choose Level 4 so Mission Control can inspect and build in local workspaces"
    Write-Host "  4. Use a lower level only when you want chat or public research without local files"
    Write-Host "  5. Send a normal message, or try: /run say exactly OK"
    Write-Host "  6. When you are ready, ask Spark how it can improve for your workflows"
    Write-Host ""
    Write-Host "If Telegram is quiet or memory is not responding:"
    Write-Host "  spark fix telegram"
    Write-Host "  spark logs spark-telegram-bot"
    Write-Host ""
    Write-Host "If Mission Control, Kanban, Canvas, or preview links are not responding:"
    Write-Host "  spark fix spawner"
    Write-Host "  spark logs spawner-ui --lines 80"
}

try {
    Invoke-Install
} finally {
    Stop-InstallLog
    Release-InstallLock
}
