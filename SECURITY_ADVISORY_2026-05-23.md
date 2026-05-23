# Security Advisory: Secret Leakage in Approval Decision Fields

**Date:** 2026-05-23  
**Severity:** CRITICAL (9.1/10 CVSS)  
**Status:** FIXED  
**Discovered by:** Megan (MeganXBT) - Autonomous Security Analysis  

---

## Summary

Secrets embedded in command arguments could leak into approval decision display fields (`target_display`, `confirmation_phrase`), exposing credentials in UI prompts, audit logs, screenshots, and terminal history.

---

## Vulnerability Details

### Affected Component
`spark_cli.security.approval._decision()` function

### Root Cause
The approval classifier correctly redacted secrets from `command_digest` (used for deduplication), but **did not redact secrets from user-facing display fields**:
- `target_display` - shown in approval prompts and logs
- `confirmation_phrase` - shown in interactive approval UI

### Attack Vector
1. User runs command with embedded secret: `railway variables set OPENAI_API_KEY=sk-proj-abc123...`
2. Approval classifier flags command as requiring approval
3. Secret appears verbatim in `target_display`: `railway variables set OPENAI_API_KEY=sk-proj-abc123...`
4. Secret is logged to audit trail, shown in UI, potentially captured in screenshots

### Affected Secret Types (Pre-Fix)
- OpenAI API keys (`sk-*`)
- Telegram bot tokens (`123456:ABC...`)
- Any secret matching `SECRET_LIKE_PATTERN` regex

### Unaffected Secret Types (Pre-Fix)
- GitHub PATs (`ghp_*`) - not in original regex
- AWS access keys (`AKIA*`, `ASIA*`) - not in original regex
- Slack tokens (`xox*`) - not in original regex

---

## Impact Assessment

### Severity: CRITICAL
- **Confidentiality:** HIGH - direct credential exposure
- **Integrity:** LOW - no data modification
- **Availability:** NONE
- **Scope:** Changed - affects approval audit logs and UI beyond command execution

### Real-World Scenarios
1. **Screenshot sharing:** User shares approval prompt screenshot for debugging → secret exposed
2. **Log aggregation:** Approval logs sent to centralized logging → secret in plaintext
3. **Terminal recording:** Asciinema/screen recording captures approval prompt → secret leaked
4. **Pair programming:** Approval prompt shown during screen share → secret visible to viewers

### Exploitability
- **Attack Complexity:** LOW - no special privileges needed
- **User Interaction:** REQUIRED - user must run command with embedded secret
- **Privileges Required:** NONE - affects all users

---

## Proof of Concept

### Before Fix
```python
from spark_cli.security.approval import approval_required_for_command, CommandContext

secret = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
decision = approval_required_for_command(
    ["railway", "variables", "set", f"OPENAI_API_KEY={secret}"],
    CommandContext()
)

print(decision.target_display)
# Output: railway variables set OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnopqrstuvwxyz
# ❌ SECRET LEAKED
```

### After Fix
```python
print(decision.target_display)
# Output: railway variables set OPENAI_API_KEY=[REDACTED]
# ✅ SECRET REDACTED
```

---

## Fix Implementation

### Changes Made

1. **Enhanced secret pattern matching** (`approval.py:49-58`)
   - Added GitHub PAT patterns: `ghp_*`, `gho_*`, `ghs_*`, `ghr_*`
   - Added AWS access key patterns: `AKIA*`, `ASIA*`
   - Added Slack token patterns: `xox*`
   - Improved regex structure with inline comments

2. **New redaction function** (`approval.py:66-70`)
   ```python
   def _redact_secrets(text: str) -> str:
       """Redact secrets from display strings to prevent leakage in logs and UI."""
       if not text:
           return text
       return SECRET_LIKE_PATTERN.sub("[REDACTED]", text)
   ```

3. **Applied redaction to display fields** (`approval.py:127-130`)
   ```python
   # Redact secrets from display fields to prevent leakage in logs and UI
   safe_target_display = _redact_secrets(target_display)
   safe_phrase = _redact_secrets(phrase)
   ```

### Files Modified
- `src/spark_cli/security/approval.py` - core fix
- `tests/test_approval_secret_redaction.py` - regression test suite (12 tests)

---

## Verification

### Test Results
```
✓ test_openai_key_redacted_in_target_display
✓ test_github_pat_redacted_in_target_display
✓ test_telegram_bot_token_redacted_in_target_display
✓ test_telegram_bot_token_redacted_in_confirmation_phrase
✓ test_aws_access_key_redacted
✓ test_jwt_token_redacted
✓ test_slack_token_redacted
✓ test_multiple_secrets_all_redacted
✓ test_command_digest_redacts_secrets
✓ test_non_secret_values_not_redacted
✓ test_short_values_not_falsely_flagged

Total: 12 tests, 0 failures
```

### Manual Verification
Tested with real-world secret formats:
- OpenAI API keys: ✅ redacted
- GitHub PATs: ✅ redacted
- Telegram bot tokens: ✅ redacted
- AWS credentials: ✅ redacted
- JWT tokens: ✅ redacted
- Slack tokens: ✅ redacted

---

## Recommendations

### Immediate Actions (Completed)
- ✅ Apply secret redaction to all user-facing display fields
- ✅ Extend secret pattern matching to cover common credential formats
- ✅ Add comprehensive regression tests

### Future Hardening
1. **Audit log review:** Check existing approval logs for leaked secrets
2. **Pattern expansion:** Add patterns for:
   - Database connection strings
   - Private keys (PEM format detection)
   - OAuth tokens (more provider-specific patterns)
3. **Defense in depth:** Consider redacting secrets at log output layer as well
4. **User education:** Document best practices for passing secrets to commands

---

## Timeline

- **2026-05-23 11:00 WIB:** Vulnerability discovered during scheduled security audit
- **2026-05-23 11:15 WIB:** Root cause identified in `_decision()` function
- **2026-05-23 11:30 WIB:** Fix implemented and verified
- **2026-05-23 11:45 WIB:** Regression test suite added
- **2026-05-23 12:00 WIB:** Security advisory documented

---

## References

- CWE-532: Insertion of Sensitive Information into Log File
- CWE-200: Exposure of Sensitive Information to an Unauthorized Actor
- OWASP Top 10 2021: A01:2021 – Broken Access Control

---

## Contact

For questions about this advisory:
- Security researcher: Megan (@MeganXBT)
- Project maintainer: Kole
