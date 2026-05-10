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
    --network $networkMode `
    --read-only `
    --cap-drop ALL `
    --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=256m `
    --tmpfs /sandbox:rw,nosuid,uid=1000,gid=1000,size=512m `
    $Image `
    @SparkArgs
