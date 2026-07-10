"""Test: setup --json output."""
import json

def test_setup_json_output_schema():
    setup_result = {
        "ok": True,
        "bundle": "telegram-starter",
        "modules_installed": 3,
        "modules_skipped": 0,
        "secrets_configured": 2,
        "autostart_enabled": True,
        "spark_started": True,
        "errors": []
    }
    output = json.dumps(setup_result, indent=2)
    parsed = json.loads(output)
    assert parsed["ok"] is True
    assert parsed["bundle"] == "telegram-starter"

def test_setup_json_error_output():
    setup_result = {
        "ok": False,
        "bundle": "telegram-starter",
        "modules_installed": 2,
        "modules_skipped": 1,
        "secrets_configured": 1,
        "autostart_enabled": False,
        "errors": [
            {"module": "spark-voice", "error": "ElevenLabs API key not provided", "severity": "warning"}
        ]
    }
    assert len(setup_result["errors"]) == 1
    assert setup_result["errors"][0]["module"] == "spark-voice"
