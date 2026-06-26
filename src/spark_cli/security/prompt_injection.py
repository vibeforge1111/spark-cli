from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


CONTEXT_FILE_NAMES = {
    ".cursorrules",
    ".windsurfrules",
    "agents.md",
    "claude.md",
    "codex.md",
    "copilot-instructions.md",
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
        re.compile(r"\b(?:ignore|disregard|forget|override)\b.{0,80}\b(?:previous|prior|system|developer|higher[- ]priority)\b.{0,80}\b(?:instructions?|prompts?|rules?)", re.IGNORECASE | re.DOTALL),
        "context file appears to tell an agent to ignore higher-priority instructions",
    ),
    (
        "prompt-injection-secret-exfiltration",
        "high",
        re.compile(r"\b(?:reveal|print|send|exfiltrate|upload|dump)\b.{0,100}\b(?:system prompt|hidden instructions|api keys?|tokens?|secrets?|\.env)\b", re.IGNORECASE | re.DOTALL),
        "context file appears to request hidden instructions or secret material",
    ),
    (
        "prompt-injection-tool-abuse",
        "medium",
        re.compile(r"\b(?:when|if)\b.{0,50}\b(?:agent|ai|assistant|llm|codex|claude)\b.{0,120}\b(?:run|execute|curl|powershell|bash|rm -rf|delete)\b", re.IGNORECASE | re.DOTALL),
        "context file appears to conditionally instruct agents to execute commands",
    ),
)


# Map of common Unicode homoglyphs to their ASCII equivalents.
# This covers Cyrillic, Greek, and other scripts that have visually 
# similar characters to Latin letters used in English.
HOMOGLYPH_MAP = {
    # Cyrillic lowercase → Latin
    '\u0430': 'a',  # а (Cyrillic)
    '\u0431': 'b',  # б (Cyrillic)
    '\u0432': 'v',  # в (Cyrillic)
    '\u0433': 'r',  # г (Cyrillic)
    '\u0435': 'e',  # е (Cyrillic)
    '\u0438': 'u',  # и (Cyrillic)
    '\u043a': 'k',  # к (Cyrillic)
    '\u043c': 'm',  # м (Cyrillic)
    '\u043e': 'o',  # о (Cyrillic)
    '\u043f': 'n',  # п (Cyrillic)
    '\u0440': 'p',  # р (Cyrillic)
    '\u0441': 'c',  # с (Cyrillic)
    '\u0442': 't',  # т (Cyrillic)
    '\u0443': 'y',  # у (Cyrillic)
    '\u0445': 'x',  # х (Cyrillic)
    '\u0446': 'c',  # ц (Cyrillic)
    '\u0448': 'w',  # ш (Cyrillic)
    '\u044b': 'b',  # ы (Cyrillic)
    '\u044d': 'e',  # э (Cyrillic)
    '\u044e': 'u',  # ю (Cyrillic)
    '\u044f': 'a',  # я (Cyrillic)
    # Cyrillic uppercase → Latin
    '\u0410': 'A',  # А
    '\u0412': 'B',  # В
    '\u0413': 'R',  # Г
    '\u0415': 'E',  # Е
    '\u0418': 'U',  # И
    '\u041a': 'K',  # К
    '\u041c': 'M',  # М
    '\u041e': 'O',  # О
    '\u041f': 'N',  # П
    '\u0420': 'P',  # Р
    '\u0421': 'C',  # С
    '\u0422': 'T',  # Т
    '\u0423': 'Y',  # У
    '\u0425': 'X',  # Х
    '\u0426': 'C',  # Ц
    '\u0428': 'W',  # Ш
    '\u042b': 'B',  # Ы
    '\u042d': 'E',  # Э
    '\u042e': 'U',  # Ю
    '\u042f': 'A',  # Я
    # Greek lowercase → Latin
    '\u03b1': 'a',  # α (alpha)
    '\u03b2': 'b',  # β (beta)
    '\u03b5': 'e',  # ε (epsilon)
    '\u03b7': 'n',  # η (eta)
    '\u03b9': 'i',  # ι (iota)
    '\u03ba': 'k',  # κ (kappa)
    '\u03bf': 'o',  # ο (omicron)
    '\u03c1': 'p',  # ρ (rho)
    '\u03c4': 't',  # τ (tau)
    '\u03c5': 'y',  # υ (upsilon)
    '\u03c7': 'x',  # χ (chi)
    # Greek uppercase → Latin
    '\u0391': 'A',  # Α
    '\u0392': 'B',  # Β
    '\u0395': 'E',  # Ε
    '\u0397': 'H',  # Η
    '\u0399': 'I',  # Ι
    '\u039a': 'K',  # Κ
    '\u039f': 'O',  # Ο
    '\u03a1': 'P',  # Ρ
    '\u03a4': 'T',  # Τ
    '\u03a5': 'Y',  # Υ
    '\u03a7': 'X',  # Χ
}


@dataclass(frozen=True)
class PromptInjectionFinding:
    category: str
    severity: str
    path: str
    detail: str


def normalize_unicode(text: str) -> str:
    """
    Normalize Unicode text using NFKD decomposition and homoglyph mapping.
    
    Unicode homoglyphs (e.g., Cyrillic 'о' U+043E vs Latin 'o' U+006F) 
    are visually similar but have different byte representations. This 
    function:
    1. Applies NFKD normalization to decompose compatibility characters
    2. Maps known homoglyphs to their ASCII equivalents
    
    This prevents bypass attacks using visually similar characters from
    other scripts (Cyrillic, Greek, etc.) to evade pattern matching.
    """
    # First apply NFKD decomposition
    normalized = unicodedata.normalize("NFKD", text)
    
    # Then map homoglyphs to ASCII equivalents
    result = []
    for char in normalized:
        result.append(HOMOGLYPH_MAP.get(char, char))
    
    return "".join(result)


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
    
    # Normalize Unicode to collapse homoglyphs before pattern matching
    normalized_text = normalize_unicode(text)
    
    for category, severity, pattern, detail in PROMPT_INJECTION_PATTERNS:
        if pattern.search(normalized_text):
            findings.append(PromptInjectionFinding(category, severity, path_label, detail))
    return findings
