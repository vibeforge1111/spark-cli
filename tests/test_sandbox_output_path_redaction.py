from __future__ import annotations

from spark_cli.sandbox.output import redact_sandbox_text


def test_sandbox_output_redacts_local_home_prefixes_without_losing_diagnostics() -> None:
    text = "\n".join(
        [
            "at /Users/alice/private/auth.py:12",
            "at /home/bob/project/worker.py:44",
            r"at C:\Users\Carol\private\cache.py:8",
        ]
    )

    redacted = redact_sandbox_text(text)

    assert "alice" not in redacted
    assert "bob" not in redacted
    assert "Carol" not in redacted
    assert "[LOCAL_HOME]/private/auth.py:12" in redacted
    assert "[LOCAL_HOME]/project/worker.py:44" in redacted
    assert r"[LOCAL_HOME]\private\cache.py:8" in redacted


def test_sandbox_output_path_redaction_does_not_rewrite_web_or_system_paths() -> None:
    text = " ".join(
        [
            "https://example.test/home/alice/report",
            "/var/log/spark/worker.log",
            "/tmp/spark-sandbox-smoke.sh",
        ]
    )

    assert redact_sandbox_text(text) == text
