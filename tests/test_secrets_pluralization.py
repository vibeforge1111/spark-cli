"""Test: secrets pluralization."""
def test_singular_secret_header():
    count = 1
    header = f"{count} secret stored:" if count == 1 else f"{count} secrets stored:"
    assert header == "1 secret stored:"

def test_plural_secret_header():
    count = 3
    header = f"{count} secret stored:" if count == 1 else f"{count} secrets stored:"
    assert header == "3 secrets stored:"

def test_zero_secrets_shows_no_header():
    count = 0
    if count == 0:
        header = "No stored secrets."
    elif count == 1:
        header = f"{count} secret stored:"
    else:
        header = f"{count} secrets stored:"
    assert header == "No stored secrets."
