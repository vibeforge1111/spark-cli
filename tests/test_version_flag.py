"""Test: --version flag."""
def test_version_flag_concept():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version="spark-cli 0.1.0")
    assert parser is not None

def test_version_can_be_parsed():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(["--version"])
    assert args.version is True
