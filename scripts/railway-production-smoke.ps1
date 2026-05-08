param(
    [string]$SparkLiveCwd = (Get-Location).Path,
    [string]$TelegramBotCwd,
    [string]$SparkLiveService = "spark-live",
    [string]$TelegramBotService = "spark-telegram-bot",
    [string]$PublicUrl = "https://spark-live-production.up.railway.app",
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
PY
'@

$checks = @(
    Invoke-Check "public_health" {
        $health = Invoke-WebRequest -UseBasicParsing "$($PublicUrl.TrimEnd('/'))/api/health/live" -TimeoutSec 20
        if ($health.StatusCode -ne 200) { throw "Expected HTTP 200, got $($health.StatusCode)" }
        "HTTP $($health.StatusCode) $($health.Content)"
    }
    Invoke-Check "spark_live_status" {
        Invoke-InCwd $SparkLiveCwd {
            $json = railway ssh --service $SparkLiveService "spark live status --json"
            $status = $json | ConvertFrom-Json
            if (-not $status.ok) { throw "spark live status reported ok=false" }
            "spark live status ok"
        }
    }
    Invoke-Check "spawner_registry_pin" {
        Invoke-InCwd $SparkLiveCwd {
            railway ssh --service $SparkLiveService $pinProbe
        }
    }
    Invoke-Check "bot_runtime_health" {
        Invoke-InCwd $TelegramBotCwd {
            railway ssh --service $TelegramBotService "npm run health:runtime"
            "bot runtime health ok"
        }
    }
    Invoke-Check "bot_to_spawner_api" {
        Invoke-InCwd $TelegramBotCwd {
            railway ssh --service $TelegramBotService $botProbe
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
