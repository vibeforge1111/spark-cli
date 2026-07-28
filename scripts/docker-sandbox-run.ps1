[CmdletBinding(PositionalBinding=$false)]
param(
    [string]$Image = "spark-cli-sandbox:local",
    [switch]$NoBuild,
    [switch]$Network,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SparkArgs
)

$ErrorActionPreference = "Stop"

if (-not $NoBuild) {
    docker build -f docker/sandbox/Dockerfile -t $Image .
}

if (-not $SparkArgs -or $SparkArgs.Count -eq 0) {
    $SparkArgs = @("--help")
}

$networkMode = "none"
if ($Network) {
    $networkMode = "bridge"
}

docker run --rm `
    --user 1000:1000 `
    --network $networkMode `
    --read-only `
    --cap-drop ALL `
    --security-opt no-new-privileges `
    --pids-limit 128 `
    --memory 512m `
    --memory-swap 512m `
    --cpus 1.0 `
    --tmpfs /tmp:rw,noexec,nosuid,size=256m `
    --tmpfs /sandbox:rw,noexec,nosuid,uid=1000,gid=1000,size=512m `
    $Image `
    @SparkArgs
