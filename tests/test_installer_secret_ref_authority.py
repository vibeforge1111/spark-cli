from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_posix_installer_confines_setup_secret_refs_to_spark_home() -> None:
    script = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")

    assert 'SPARK_SECRET_DIR="$SPARK_PREFIX/state/setup-secret-inputs"' in script
    assert 'chmod 700 "$SPARK_SECRET_DIR"' in script
    assert 'mktemp "$SPARK_SECRET_DIR/spark-secret.XXXXXX"' in script
    assert 'chmod 600 "$secret_file"' in script
    assert 'SPARK_SECRET_FILES+=("$secret_file")' in script
    assert 'rm -f "${SPARK_SECRET_FILES[@]}"' in script
    assert 'rm -rf "$SPARK_SECRET_DIR"' in script


def test_powershell_installer_confines_and_cleans_setup_secret_refs() -> None:
    script = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")

    assert '$secretDir = Join-Path $Script:SparkPrefix "state\\setup-secret-inputs"' in script
    assert "[System.IO.Path]::GetRandomFileName()" in script
    assert "[System.IO.File]::WriteAllText($secretFile, $Value" in script
    assert "[void]$secretFiles.Add($secretFile)" in script
    assert "Remove-Item -LiteralPath $secretFile -Force" in script
    assert "Remove-Item -LiteralPath $secretDir -Force" in script
