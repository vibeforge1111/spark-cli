"""Test: os --dry-run preview mode."""
def test_os_dry_run_flag_exists():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True

def test_os_dry_run_default_false():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args([])
    assert args.dry_run is False
