from __future__ import annotations

import re
from pathlib import Path

_FIXTURE_DIRS = {"test", "tests", "__tests__", "fixture", "fixtures"}
_PRIVATE_KEY_MARKER = r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
_HELPER = r"(?:redact\w*|scrub\w*|sanitize\w*|sanitise\w*|maskSecrets?)"
_DIRECT_PRIVATE_KEY_FIXTURE = re.compile(
    rf"{_HELPER}\s*\(\s*[\"'`][^\"'`]*{_PRIVATE_KEY_MARKER}",
    re.IGNORECASE,
)
_ARRAY_PRIVATE_KEY_FIXTURE = re.compile(
    rf"\bconst\s+(?P<array>[A-Za-z_$][\w$]*)\s*=\s*\[[\s\S]{{0,20000}}?"
    rf"{_PRIVATE_KEY_MARKER}[\s\S]{{0,20000}}?\]\s*;",
    re.IGNORECASE,
)


def is_redaction_fixture_private_key(path_label: str, text: str) -> bool:
    if not ({part.lower() for part in Path(path_label).parts} & _FIXTURE_DIRS):
        return False
    if _DIRECT_PRIVATE_KEY_FIXTURE.search(text):
        return True
    for match in _ARRAY_PRIVATE_KEY_FIXTURE.finditer(text):
        array_name = re.escape(match.group("array"))
        loop = re.compile(
            rf"for\s*\(\s*const\s+(?P<item>[A-Za-z_$][\w$]*)\s+of\s+{array_name}\s*\)"
            rf"\s*\{{(?P<body>[\s\S]{{0,8000}}?)\}}",
            re.IGNORECASE,
        )
        for loop_match in loop.finditer(text):
            item = re.escape(loop_match.group("item"))
            if re.search(rf"{_HELPER}\s*\(\s*{item}\s*\)", loop_match.group("body"), re.IGNORECASE):
                return True
    return False
