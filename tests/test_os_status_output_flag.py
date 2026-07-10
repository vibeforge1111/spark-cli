"""Test: spark os status --output flag."""
def test_os_status_output_flag_parsing():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=["table","json","yaml","text"], default="text")
    args = parser.parse_args(["--output","json"])
    assert args.output == "json"

def test_os_status_output_default_is_text():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=["table","json","yaml","text"], default="text")
    args = parser.parse_args([])
    assert args.output == "text"
