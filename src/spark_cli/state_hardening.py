from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Iterable


STATE_DIRECTORY_HARDENING_WARNING = (
    "spark-cli: could not enforce owner-only permissions for local Spark state; "
    "inspect local access before continuing.\n"
)


def ensure_private_directories(paths: Iterable[Path]) -> None:
    failed = False
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path, 0o700)
        except OSError:
            failed = True
    if failed:
        sys.stderr.write(STATE_DIRECTORY_HARDENING_WARNING)
