from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


CONTEXT_FILE_NAMES = {
    ".cursorrules",
    "agents.md",
    "claude.md",
    "codex.md",
    "gemini.md",
    "instructions.md",
    "llms-full.txt",
    "llms.txt",
    "readme.md",
}

CONTEXT_FILE_SUFFIXES = {".md", ".mdx", ".txt", ".rst"}

PROMPT_INJECTION_PATTERNS = (
    (
        "prompt-injection-override",
        "medium",
        re.compile(r"\b(?:ignore|disregard|forget|override|neglect|dismiss|skip|omit|discard|bypass)\b.{0,80}?\b(?:previous|prior|system|developer|higher[- ]priority)\b.{0,80}?\b(?:instructions?|prompts?|rules?)", re.IGNORECASE | re.DOTALL),
        "context file appears to tell an agent to ignore higher-priority instructions",
    ),
    (
        "prompt-injection-secret-exfiltration",
        "high",
        re.compile(r"\b(?:reveal|print|send|exfiltrate|upload|dump)\b.{0,100}?\b(?:system prompt|hidden instructions|api keys?|tokens?|secrets?|\.env)\b", re.IGNORECASE | re.DOTALL),
        "context file appears to request hidden instructions or secret material",
    ),
    (
        "prompt-injection-tool-abuse",
        "medium",
        re.compile(r"\b(?:when|if)\b.{0,50}?\b(?:agent|ai|assistant|llm|codex|claude)\b.{0,120}?\b(?:run|execute|curl|powershell|bash|rm -rf|delete)\b", re.IGNORECASE | re.DOTALL),
        "context file appears to conditionally instruct agents to execute commands",
    ),
)


@dataclass(frozen=True)
class PromptInjectionFinding:
    category: str
    severity: str
    path: str
    detail: str


def is_agent_context_path(path_label: str) -> bool:
    path = Path(path_label)
    name = path.name.lower()
    if name in CONTEXT_FILE_NAMES:
        return True
    if path.suffix.lower() not in CONTEXT_FILE_SUFFIXES:
        return False
    return any(part.lower() in {"docs", ".github", "prompts", "instructions"} for part in path.parts)


def scan_prompt_injection_text(path_label: str, text: str) -> list[PromptInjectionFinding]:
    if not is_agent_context_path(path_label):
        return []
    findings: list[PromptInjectionFinding] = []
    for category, severity, pattern, detail in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(PromptInjectionFinding(category, severity, path_label, detail))
    return findings
