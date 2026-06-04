from __future__ import annotations

import re
from dataclasses import dataclass


CONTROL_SEQUENCE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DEFAULT_MAX_BYTES = 32_768
DEFAULT_MAX_LINES = 200

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\b\s*=\s*([^\s]+)"),
    re.compile(r'(?i)"(?:apiKey|token|secret|password|passwd|accessToken|refreshToken)"\s*:\s*"([^"]+)"'),
    re.compile(r"(?i)--(?:api[-_]?key|token|secret|password|passwd)\s+([^\s]+)"),
    re.compile(r"(?i)\b(?:X-Api-Key|X-Auth-Token|Cookie|Set-Cookie)\s*[:=]\s*([^\r\n;]+)"),
    re.compile(r"(?i)Authorization\s*[:=]\s*Basic\s+([A-Za-z0-9._\-+=/]+)"),
    re.compile(r"(?i)Authorization\s*[:=]\s*Bearer\s+([A-Za-z0-9._\-+=]+)"),
    re.compile(r"(?i)Authorization\s*[:=]\s*(?:Token|ApiKey|Api-Key|OAuth)\s+([^\r\n;]+)"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^@\s/]+)@"),
    re.compile(r"(?i)([?&](?:access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|sig|signature)=)([^&#\s]+)"),
    re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._\-+=]{18,})\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})\b"),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
    re.compile(r"\b(hf_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(AIza[0-9A-Za-z_\-]{25,})\b"),
    re.compile(r"\b(AKI[AI][A-Z0-9]{16})\b"),
    re.compile(r"\b(gh[oprsu]_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(glpat-[A-Za-z0-9_\-]{20,})\b"),
    re.compile(r"\b(npm_[A-Za-z0-9]{10,})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{20,})\b"),
    re.compile(r"\bbot(\d{6,}:[A-Za-z0-9_-]{20,})\b"),
    re.compile(r"\b(\d{6,}:[A-Za-z0-9_-]{20,})\b"),
)


@dataclass(frozen=True)
class BoundedOutput:
    text: str
    truncated: bool
    original_bytes: int
    original_lines: int

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "truncated": self.truncated,
            "original_bytes": self.original_bytes,
            "original_lines": self.original_lines,
        }


def strip_terminal_controls(text: str) -> str:
    without_sequences = CONTROL_SEQUENCE_RE.sub("", text)
    return CONTROL_CHAR_RE.sub("", without_sequences)


def _mask_secret(value: str) -> str:
    if "PRIVATE KEY-----" in value:
        lines = [line for line in value.splitlines() if line]
        if len(lines) >= 2:
            return f"{lines[0]}\n[REDACTED]\n{lines[-1]}"
        return "[REDACTED]"
    if len(value) <= 10:
        return "[REDACTED]"
    return f"{value[:4]}...[REDACTED]...{value[-4:]}"


def redact_sandbox_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            if match.lastindex:
                secret = match.group(match.lastindex)
                return match.group(0).replace(secret, _mask_secret(secret))
            return _mask_secret(match.group(0))

        redacted = pattern.sub(replace, redacted)
    return redacted


def _decode_utf8_prefix(data: bytes) -> str:
    prefix = data
    while prefix:
        try:
            return prefix.decode("utf-8")
        except UnicodeDecodeError as exc:
            prefix = prefix[: exc.start]
    return ""


def bound_sandbox_output(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> BoundedOutput:
    safe = redact_sandbox_text(strip_terminal_controls(text))
    lines = safe.splitlines()
    encoded = safe.encode("utf-8", errors="replace")
    truncated = len(encoded) > max_bytes or len(lines) > max_lines
    next_text = "\n".join(lines[:max_lines])
    next_bytes = next_text.encode("utf-8", errors="replace")
    if len(next_bytes) > max_bytes:
        next_text = _decode_utf8_prefix(next_bytes[:max_bytes])
    if truncated:
        next_text = f"{next_text}\n[output truncated]"
    return BoundedOutput(
        text=next_text,
        truncated=truncated,
        original_bytes=len(encoded),
        original_lines=len(lines),
    )
