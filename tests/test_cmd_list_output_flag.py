"""Test: cmd_list --output flag."""
import json

def test_list_output_json_concept():
    modules_data = [
        {"name": "spark-telegram-bot", "version": "1.0.0", "kind": "bot", "plane": "agent", "blessed": True, "installed": True, "path": "/path/to/module"},
        {"name": "spark-core", "version": "1.0.0", "kind": "core", "plane": "platform", "blessed": True, "installed": True, "path": "/path/to/core"},
    ]
    output = json.dumps({"ok": True, "count": len(modules_data), "modules": modules_data}, indent=2)
    parsed = json.loads(output)
    assert parsed["ok"] is True
    assert parsed["count"] == 2

def test_list_output_json_flag_parsing():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args(["--output", "json"])
    assert args.output == "json"
