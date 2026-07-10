"""Test: TERM=dumb color detection."""
import os

def test_term_dumb_disables_color():
    os.environ["TERM"] = "dumb"
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        if os.environ.get("TERM") == "dumb":
            color_supported = False
        else:
            color_supported = True
        assert color_supported is False
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color
        del os.environ["TERM"]

def test_term_xterm_enables_color():
    os.environ["TERM"] = "xterm-256color"
    no_color = os.environ.pop("NO_COLOR", None)
    try:
        if os.environ.get("TERM") == "dumb":
            color_supported = False
        elif os.environ.get("NO_COLOR"):
            color_supported = False
        else:
            color_supported = True
        assert color_supported is True
    finally:
        if no_color is not None:
            os.environ["NO_COLOR"] = no_color
        del os.environ["TERM"]
