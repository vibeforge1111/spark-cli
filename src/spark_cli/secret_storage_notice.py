from __future__ import annotations

import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def warn_insecure_file_secret_storage() -> None:
    print(
        "⚠️ Insecure local secret storage is active: values are encoded, not encrypted. "
        "Other processes with access can read them; use this mode only for disposable local testing.",
        file=sys.stderr,
    )
