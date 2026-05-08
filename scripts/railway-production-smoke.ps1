param(
    [string]$SparkLiveCwd = (Get-Location).Path,
    [string]$TelegramBotCwd,
    [string]$SparkLiveService = "spark-live",
    [string]$TelegramBotService = "spark-telegram-bot",
    [string]$PublicUrl = "https://spark-live-production.up.railway.app",
    [int]$RetryCount = 6,
    [int]$RetryDelaySeconds = 10,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    @"
Spark Railway production smoke

Required:
  -SparkLiveCwd      Directory linked to the Railway Spark Live project
  -TelegramBotCwd    Directory linked to the Railway Telegram bot project

Example:
  .\scripts\railway-production-smoke.ps1 `
    -SparkLiveCwd C:\path\to\spark-cli-prod-worktree `
    -TelegramBotCwd C:\path\to\spark-telegram-bot
"@
    exit 0
}

if (-not $TelegramBotCwd) {
    throw "TelegramBotCwd is required because the bot and Spark Live services usually live in different Railway projects."
}

function Invoke-InCwd {
    param(
        [string]$Cwd,
        [scriptblock]$Block
    )
    Push-Location $Cwd
    try {
        & $Block
    } finally {
        Pop-Location
    }
}

function Invoke-Check {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    try {
        $detail = & $Block
        [pscustomobject]@{ name = $Name; ok = $true; detail = ($detail -join "`n") }
    } catch {
        [pscustomobject]@{ name = $Name; ok = $false; detail = $_.Exception.Message }
    }
}

function Assert-RemoteMarker {
    param(
        [string]$Name,
        [string[]]$Output
    )
    $text = $Output -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "$Name remote command exited with $LASTEXITCODE. $($text.Trim())"
    }
    if ($text -notmatch "__SPARK_SMOKE_OK__") {
        throw "$Name remote command did not emit completion marker. $($text.Trim())"
    }
    $Output | Where-Object { $_ -notmatch "__SPARK_SMOKE_OK__" }
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Block
    )
    $lastError = $null
    for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
        try {
            return & $Block
        } catch {
            $lastError = $_.Exception.Message
            if ($attempt -lt $RetryCount) {
                Start-Sleep -Seconds $RetryDelaySeconds
            }
        }
    }
    throw $lastError
}

$botProbe = @'
node - <<'NODE'
const base = process.env.SPAWNER_UI_URL;
const headers = {};
if (process.env.SPARK_BRIDGE_API_KEY) headers['x-api-key'] = process.env.SPARK_BRIDGE_API_KEY;
if (process.env.SPARK_UI_API_KEY) headers['x-spawner-ui-key'] = process.env.SPARK_UI_API_KEY;
if (process.env.SPARK_WORKSPACE_ID) headers['x-spawner-workspace-id'] = process.env.SPARK_WORKSPACE_ID;
if (!base) throw new Error('SPAWNER_UI_URL is not configured');
for (const path of ['/api/health/live', '/api/providers', '/api/mission-control/board']) {
  const res = await fetch(base + path, { headers });
  const text = await res.text();
  if (!res.ok) throw new Error(`${path} returned ${res.status}: ${text.slice(0, 160)}`);
  console.log(`${path} ${res.status}`);
}
console.log('__SPARK_SMOKE_OK__');
NODE
'@

$pinProbe = @'
python3 - <<'PY'
import json
from pathlib import Path
path = Path('/data/spark/state/installed.json')
data = json.loads(path.read_text())
spawner = data.get('spawner-ui') or {}
commit = spawner.get('registry_commit')
if not commit:
    raise SystemExit('spawner-ui registry_commit missing')
print('spawner-ui registry_commit=' + commit)
print('__SPARK_SMOKE_OK__')
PY
'@

$checks = @(
    Invoke-Check "public_health" {
        Invoke-WithRetry {
            $health = Invoke-WebRequest -UseBasicParsing "$($PublicUrl.TrimEnd('/'))/api/health/live" -TimeoutSec 20
            if ($health.StatusCode -ne 200) { throw "Expected HTTP 200, got $($health.StatusCode)" }
            "HTTP $($health.StatusCode) $($health.Content)"
        }
    }
    Invoke-Check "spark_live_status" {
        Invoke-WithRetry {
          Invoke-InCwd $SparkLiveCwd {
            $json = railway ssh --service $SparkLiveService "spark live status --json"
            $status = $json | ConvertFrom-Json
            if (-not $status.ok) { throw "spark live status reported ok=false" }
            "spark live status ok"
          }
        }
    }
    Invoke-Check "spawner_registry_pin" {
        Invoke-InCwd $SparkLiveCwd {
            $output = railway ssh --service $SparkLiveService $pinProbe 2>&1
            Assert-RemoteMarker "spawner_registry_pin" $output
        }
    }
    Invoke-Check "bot_runtime_health" {
        Invoke-InCwd $TelegramBotCwd {
            $output = railway ssh --service $TelegramBotService "npm run health:runtime && echo __SPARK_SMOKE_OK__" 2>&1
            Assert-RemoteMarker "bot_runtime_health" $output
            "bot runtime health ok"
        }
    }
    Invoke-Check "bot_to_spawner_api" {
        Invoke-WithRetry {
          Invoke-InCwd $TelegramBotCwd {
              $output = railway ssh --service $TelegramBotService $botProbe 2>&1
              Assert-RemoteMarker "bot_to_spawner_api" $output
          }
        }
    }
)

$ok = $true
foreach ($check in $checks) {
    $marker = if ($check.ok) { "[OK]" } else { "[FIX]" }
    Write-Host "$marker $($check.name): $($check.detail)"
    if (-not $check.ok) { $ok = $false }
}

if (-not $ok) {
    exit 1
}
