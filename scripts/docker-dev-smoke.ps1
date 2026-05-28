param(
    [string]$Image = "spark-cli-dev:local",
    [switch]$NoBuild,
    [switch]$RegistryPins,
    [switch]$Provenance,
    [string]$Command = "python -m pytest tests/test_docker_entrypoint.py -q && spark --help >/tmp/spark-help.txt"
)

$ErrorActionPreference = "Stop"

if ($RegistryPins) {
    $Command = "$Command && python -m spark_cli.cli verify --registry-pins --json"
}

if ($Provenance) {
    $Command = "$Command && python -m spark_cli.cli verify --provenance --json"
}

if (-not $NoBuild) {
    docker build -f docker/dev/Dockerfile -t $Image .
}

docker run --rm `
    -e SPARK_HOME=/tmp/spark-home `
    $Image `
    bash -lc $Command
