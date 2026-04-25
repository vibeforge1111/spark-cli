param(
    [string]$Prefix = "$HOME\.spark",
    [string]$Source = "https://github.com/vibeforge1111/spark-cli",
    [string]$Ref = "",
    [string]$NodeVersion = "22.18.0",
    [string]$Bundle = "telegram-starter",
    [string[]]$SetupArg = @(),
    [string]$LocalRegistry = "",
    [switch]$SkipSetup,
    [switch]$NoAutostart
)

$ErrorActionPreference = "Stop"

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

function Install-Node {
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
        git -C $target fetch --depth=1 origin $(if ($Ref) { $Ref } else { "HEAD" })
    } else {
        if (Test-Path $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
        Write-SparkLog "Cloning spark-cli from $Source"
        git clone --depth=1 $Source $target
    }
    if ($Ref) {
        git -C $target checkout $Ref
    }
    return $target
}

function Install-CliVenv {
    param([string]$CliDir)
    $venvDir = Join-Path $Script:SparkPrefix "tools\spark-cli-venv"
    Write-SparkLog "Creating Spark CLI virtualenv"
    python -m venv $venvDir
    & (Join-Path $venvDir "Scripts\python.exe") -m pip install --upgrade pip | Out-Null
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
    Write-SparkLog "Running spark setup $Bundle"
    & $sparkCmd setup $Bundle @SetupArg
    if ($LASTEXITCODE -ne 0) {
        throw "spark setup failed with exit code $LASTEXITCODE"
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
$Script:SparkPrefix = Resolve-FullPath $Prefix
New-Item -ItemType Directory -Force -Path $Script:SparkPrefix | Out-Null
$nodeDir = Install-Node
$env:PATH = "$nodeDir;$env:PATH"
Write-SparkLog "Node runtime: $(& (Join-Path $nodeDir "node.exe") -v)"
$cliDir = Checkout-Cli
$venvDir = Install-CliVenv -CliDir $cliDir
Write-Wrapper -NodeDir $nodeDir -VenvDir $venvDir
Add-SparkBinToUserPath
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
Write-Host "  spark verify"
Write-Host "  spark autostart status"
Write-Host ""
Write-Host "If Telegram is quiet or memory is not responding:"
Write-Host "  spark fix telegram"
Write-Host "  spark logs spark-telegram-bot"
