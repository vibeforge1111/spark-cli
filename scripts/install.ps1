param(
    [string]$Prefix = "$HOME\.spark",
    [string]$Source = "https://github.com/vibeforge1111/spark-cli",
    [string]$Ref = "cacca70220360c4b20b310486251003cee1e349e",
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
    [switch]$NoAutostart,
    [switch]$AllowDevSource,
    [switch]$DryRun,
    [switch]$Preflight,
    [switch]$Yes,
    [switch]$UpgradeExisting
)

$ErrorActionPreference = "Stop"
$SparkCliReleaseName = "spark-cli-launch-2026-05-09"
$RefWasProvided = $PSBoundParameters.ContainsKey("Ref")
$Script:InstallLockDir = ""
$Script:PythonExe = ""
$Script:UvExe = ""
$Script:InstallLogPath = ""
$Script:TranscriptStarted = $false

function Write-SparkLog {
    param([string]$Message)
    Write-Host "[spark-install] $Message"
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
    foreach ($name in @("python", "python3")) {
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
        $Script:UvExe = $cmd.Source
        return $true
    }
    foreach ($candidate in @(
        (Join-Path $HOME ".local\bin\uv.exe"),
        (Join-Path $HOME ".cargo\bin\uv.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) {
            $Script:UvExe = $candidate
            return $true
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
    if (Test-Path -LiteralPath $uvExe) {
        $Script:UvExe = $uvExe
        Write-SparkLog "Using managed uv at $Script:UvExe"
        return
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
    Write-SparkLog "Autostart: $(-not $NoAutostart)"
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
    $autostartEnabled = if ($NoAutostart) { "no" } else { "yes" }
    $existing = if (Test-ExistingInstall) { "detected" } else { "none" }
    $existingMode = if ($UpgradeExisting) { "upgrade" } else { "abort" }
    Write-Host "Spark install preview"
    Write-Host "Nothing has changed yet."
    Write-Host ""
    Write-Host "Spark will:"
    Write-Host "  1. Install the Spark command"
    Write-Host "  2. Connect your Telegram bot"
    Write-Host "  3. Help you choose an AI provider"
    Write-Host "  4. Start Spark"
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
        if ($AdminTelegramIds) { $setupPreviewArgs += @("--admin-telegram-ids", $AdminTelegramIds) }
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
    if (-not $RefWasProvided -and $Ref -notmatch '^[0-9a-f]{40}$') {
        throw "Default Spark CLI ref must be an immutable 40-character commit SHA: $Ref"
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
    Write-SparkLog "Creating Spark CLI virtualenv"
    & $Script:PythonExe -m venv $venvDir
    Write-SparkLog "Upgrading pip in Spark CLI virtualenv"
    & (Join-Path $venvDir "Scripts\python.exe") -m pip install --upgrade pip | Out-Null
    Write-SparkLog "Installing Spark CLI package"
    & (Join-Path $venvDir "Scripts\python.exe") -m pip install -e $CliDir | Out-Null
    return $venvDir
}

function Write-Wrapper {
    param([string]$NodeDir, [string]$VenvDir)
    $binDir = Join-Path $Script:SparkPrefix "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $wrapper = Join-Path $binDir "spark.cmd"
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
        Write-Host ""
        Write-Host "Next:"
        Write-Host "  $Script:SparkPrefix\bin\spark.cmd setup $Bundle"
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
    try {
        $setupStartArgs = if ($NoAutostart) { @("--no-start-now", "--no-autostart") } else { @("--start-now", "--autostart") }
        & $sparkCmd setup $Bundle @setupStartArgs @setupArgs
        if ($LASTEXITCODE -ne 0) {
            throw "spark setup failed with exit code $LASTEXITCODE"
        }
    } finally {
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

function Invoke-Install {
    $Script:SparkPrefix = Resolve-FullPath $Prefix
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
    Write-Host "Install log:"
    Write-Host "  $Script:InstallLogPath"
    Write-Host ""
    Write-Host "Finish in Telegram:"
    Write-Host "  1. Open your Spark bot and send /start"
    Write-Host "  2. For first builds, choose Level 4 so Mission Control can inspect and build in local workspaces"
    Write-Host "  3. Use a lower level only when you want chat, memory, diagnostics, public research, or remote missions without local files"
    Write-Host "  4. Send /diagnose"
    Write-Host "  5. Try memory: /remember I like concise warm replies"
    Write-Host "  6. Try a tiny build: /run say exactly OK"
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
