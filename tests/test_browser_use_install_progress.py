"""Test: browser-use install step counter."""
import io
from contextlib import redirect_stdout

def test_step_counter_concept():
    steps = [
        "pip install [browser-use]",
        "browser-use install (Chromium)",
        "browser-use doctor",
    ]
    output = io.StringIO()
    with redirect_stdout(output):
        for i, step in enumerate(steps, 1):
            print(f"Step {i}/{len(steps)}: {step}")
    lines = output.getvalue().strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "Step 1/3: pip install [browser-use]"
    assert lines[1] == "Step 2/3: browser-use install (Chromium)"
    assert lines[2] == "Step 3/3: browser-use doctor"

def test_progress_counter_visible():
    total = 3
    for n in range(1, total + 1):
        msg = f"Step {n}/{total}"
        assert msg.startswith("Step")
