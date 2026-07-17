from __future__ import annotations

import pytest

from spark_cli.sandbox.paths import validate_target_name


@pytest.mark.parametrize(
    "rejected",
    [
        "../../Users/alice/private/token.txt",
        "bad-name\nsecret-shaped-value",
        "con",
    ],
)
def test_target_name_validation_does_not_reflect_rejected_input(rejected: str) -> None:
    with pytest.raises(ValueError) as raised:
        validate_target_name(rejected)

    message = str(raised.value)
    assert rejected not in message
    assert "alice" not in message
    assert "secret-shaped-value" not in message
    assert "Target name" in message
