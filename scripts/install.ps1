param(
    [string]$Prefix = "$HOME\.spark",
    [string]$Source = "https://github.com/vibeforge1111/spark-cli",
    [string]$Ref = "spark-cli-launch-2026-04-27-2",
    [string]$NodeVersion = "22.18.0",
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
    [switch]$AllowDevSource
)

$ErrorActionPreference = "Stop"
$RefWasProvided = $PSBoundParameters.ContainsKey("Ref")

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

function Require-PythonVersion {
    $versionText = (& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
    & python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' | Out-Null
    $ok = $LASTEXITCODE
    if ($ok -ne 0) {
        throw "Python >= 3.11 is required for Spark. Found Python $versionText. Install a newer Python and rerun the installer."
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
        git clone --depth=1 $Source $target
    }
    Checkout-CliRef -Target $target
    return $target
}

function Install-CliVenv {
    param([string]$CliDir)
    $venvDir = Join-Path $Script:SparkPrefix "tools\spark-cli-venv"
    Write-SparkLog "Creating Spark CLI virtualenv"
    python -m venv $venvDir
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
        & $sparkCmd setup $Bundle @setupArgs
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
    $sparkCmd = Join-Path $Script:SparkPrefix "bin\spark.cmd"
    if ($NoAutostart) {
        Write-SparkLog "Skipping Spark autostart"
        Write-Host ""
        Write-Host "To start Spark manually:"
        Write-Host "  $sparkCmd start $Bundle"
        return
    }

    Write-SparkLog "Installing Spark autostart"
    & $sparkCmd autostart install $Bundle --now
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Spark autostart could not be enabled automatically."
        Write-Host ""
        Write-Host "Manual fallback for this session:"
        Write-Host "  $sparkCmd start $Bundle"
        Write-Host ""
        Write-Host "To try autostart again:"
        Write-Host "  $sparkCmd autostart install --now"
    }
}

Require-Command python
Require-PythonVersion
$Script:SparkPrefix = Resolve-FullPath $Prefix
Test-InstallSettings
New-Item -ItemType Directory -Force -Path $Script:SparkPrefix | Out-Null
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
Write-Host "  spark status"
Write-Host "  spark providers status"
Write-Host "  spark verify --onboarding"
Write-Host "  spark autostart status"
Write-Host ""
Write-Host "Finish in Telegram:"
Write-Host "  1. Open your Spark bot and send /start"
Write-Host "  2. Pick an access level when Spark asks. Most people should use /access 3"
Write-Host "  3. Send /diagnose"
Write-Host "  4. Try memory: /remember I like concise warm replies"
Write-Host "  5. Try a tiny build: /run say exactly OK"
Write-Host ""
Write-Host "If Telegram is quiet or memory is not responding:"
Write-Host "  spark fix telegram"
Write-Host "  spark logs spark-telegram-bot"
