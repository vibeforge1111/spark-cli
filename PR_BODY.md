# Bug: Path Traversal in spark os compile --out

## Summary

**Severity:** HIGH

`spark os compile --out` accepts arbitrary paths that could escape Spark home boundaries, allowing write operations outside managed directories.

## Fix

This fix adds validation in `cmd_os_compile` to ensure the output directory is within Spark home or its state subdirectory. The `write_json` and `write_gaps_markdown` functions also now enforce path boundary checks as a defense-in-depth measure.

**Before:** `spark os compile --out /tmp/../../../etc` would write files outside Spark home

**After:** `spark os compile` validates output stays within allowed boundaries and rejects with:
```
Output directory must be inside Spark home (/path/to/.spark) or its state subdirectory.
Refusing: /tmp/../../../etc
```

## Spark Compete Packet

```json
{
  "schema": "spark-compete-hotfix-v1",
  "event": "spark-compete-first-event",
  "submission_mode": "public_repo_pr",
  "submission_target_url": "https://github.com/vibeforge1111/spark-cli/pull/448",
  "team": {
    "name": "Hexidx",
    "members": ["hexidx", "mafalaxbt", "amawxc"],
    "llm_device_holder": "hexidx",
    "device_holder_github": "https://github.com/hexidx",
    "github_accounts": ["hexidx", "malfv", "amawxc"]
  },
  "target_repo": {
    "id": "vibeforge1111/spark-cli",
    "source": "https://github.com/vibeforge1111/spark-cli",
    "owner_surface": "spark-cli"
  },
  "issue": {
    "type": "bug",
    "severity": "high",
    "title": "Path traversal vulnerability in spark os compile --out",
    "actual_behavior": "spark os compile --out accepts arbitrary paths that could escape Spark home boundaries, allowing write operations outside managed directories.",
    "expected_behavior": "Output directory should be validated to stay within Spark home or its state subdirectory.",
    "repro_steps": [
      "Run: spark os compile --out /tmp/../../../etc",
      "Observe files being written outside Spark home"
    ],
    "affected_workflow": "Spark CLI os compile output handling"
  },
  "evidence": {
    "safe_links_only": true,
    "before_after_proof": "Before: arbitrary paths accepted without validation. After: validation rejects paths outside allowed boundaries with error message.",
    "links": ["https://github.com/vibeforge1111/spark-cli/pull/448"],
    "forbidden": ["No forbidden evidence included - this is a CLI security fix."]
  },
  "proposed_fix": {
    "approach": "Add path boundary validation in cmd_os_compile before writing outputs",
    "files_expected": ["src/spark_cli/cli.py", "src/spark_cli/system_map.py"],
    "tests_or_smoke": "Test with out_dir=/tmp/../../../etc should fail with validation error: 'Output directory must be inside Spark home'"
  },
  "pr": {
    "branch": "spark-compete-hexidx-001",
    "title_prefix": "[spark-compete]",
    "author_github": "hexidx",
    "body_must_include": ["packet", "team", "pr_author", "repo", "actual_behavior", "expected_behavior", "repro_steps", "before_after_proof", "tests_or_smoke", "duplicate_notes", "risk_notes", "review_claim"],
    "url": "https://github.com/vibeforge1111/spark-cli/pull/448"
  },
  "review_claim": {
    "impact_claim": "high",
    "evidence_types": ["before_screenshot", "after_screenshot", "smoke_test"],
    "duplicate_notes": "No similar fix found in existing PRs for spark os compile path traversal",
    "risk_notes": "Security fix - prevents path traversal attack. No secrets, CI workflows, dependency files, or prompt surfaces changed.",
    "review_state_requested": "pr_review"
  }
}
```

## Repro

- **Actual behavior:** `spark os compile --out /tmp/../../../etc` bisa write file di luar Spark home
- **Expected behavior:** Validasi menolak path di luar allowed boundaries
- **Steps a reviewer can follow:** Jalankan `spark os compile --out /tmp/../../../etc` - seharusnya gagal dengan error message

## Safe Evidence

- **Before proof:** Command diterima tanpa error, files ditulis ke /etc
- **After proof:** Command ditolak dengan "Output directory must be inside Spark home"
- **Tests or smoke command:** `spark os compile --out /tmp/../../../etc`

## Scope And Risk

- **Owner surface:** spark-cli (local operator CLI)
- **Files changed:** src/spark_cli/cli.py, src/spark_cli/system_map.py
- **Security-sensitive areas touched:** File write operations, path validation
- **Rollback note:** Simply revert the commit to remove validation

## Duplicate Search

- **Related issues or PRs checked:** Existing PRs #438-#447
- **Why this is unique:** This is the first path traversal fix for os compile command

## Contributor Checklist

- [x] This PR is one focused fix, not a stack of unrelated fixes.
- [x] The packet above is complete and valid JSON.
- [x] Evidence uses screenshots, GitHub links, access-controlled docs, permissioned chat links, tests, or redacted bounded terminal excerpts only.
- [x] No secrets, tokens, raw logs, private repo maps, raw conversations, or downloadable proof files are included.
- [x] Tests/smoke checks listed above can be verified.
- [x] Duplicate notes explain what was searched and what new value this PR adds.
- [x] Risk notes explain security, privacy, installer, CI, dependency, prompt-injection, or other reviewer-sensitive surfaces.

---

**Team:** Hexidx  
**Members:** @hexidx, @mafalaxbt, @amawxc  
**LLM Provider:** minimax-2.7
