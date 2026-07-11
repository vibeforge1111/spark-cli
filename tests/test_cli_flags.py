import subprocess
def test_spark_list():
    r = subprocess.run(["python3","-m","spark_cli.cli","list","--json"], capture_output=True, timeout=5)
    assert r.returncode in (0,2)
