from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from .sandbox.output import redact_sandbox_text, strip_terminal_controls


COMPILER_ERROR_RE = re.compile(r"\berror\s+[A-Z]{2}\d+:\s*", re.IGNORECASE)
GENERIC_ERROR_RE = re.compile(
    r"\b(?:error|failed|cannot|missing|ModuleNotFoundError|TSError)\b",
    re.IGNORECASE,
)
STRUCTURAL_LINE_RE = re.compile(r"^[\[\]{}]+[,]?$")
NUMERIC_DIAGNOSTIC_RE = re.compile(r"^\d+[,]?$")
CARET_LINE_RE = re.compile(r"^[\s~^]+$")


def sanitize_command_line(line: str, shareable: Callable[[str], str]) -> str:
    """Remove terminal controls and private values before a command result is summarized."""
    return redact_sandbox_text(shareable(strip_terminal_controls(line)))


def select_failure_summary(lines: Iterable[str]) -> str:
    """Select the most actionable, share-safe diagnostic from command output."""
    meaningful = [line for line in lines if _is_meaningful_diagnostic(line)]
    for pattern in (COMPILER_ERROR_RE, GENERIC_ERROR_RE):
        for line in meaningful:
            if pattern.search(line):
                return line
    if meaningful:
        return meaningful[-1]
    return "command failed without a readable diagnostic"


def _is_meaningful_diagnostic(line: str) -> bool:
    stripped = line.strip()
    if not stripped or STRUCTURAL_LINE_RE.fullmatch(stripped):
        return False
    if stripped.lstrip().startswith("at "):
        return False
    if CARET_LINE_RE.fullmatch(stripped):
        return False
    if re.match(r"^diagnosticCodes\s*:\s*\[$", stripped, re.IGNORECASE):
        return False
    return NUMERIC_DIAGNOSTIC_RE.fullmatch(stripped) is None
