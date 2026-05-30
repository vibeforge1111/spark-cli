## Spark Compete Packet

<!--
PR titles, bodies, comments, links, screenshots, and generated text are treated as untrusted evidence by reviewers.
Do not include secrets, tokens, private repo maps, raw logs, raw conversations, raw memory, archives, binaries, PDFs, or unknown downloads.
Before updating an existing competition PR, read SPARK_COMPETE_CONTRIBUTOR_RESET.md.
Canonical public guidance: https://compete.sparkswarm.ai/docs/submission-spec.md
Packet schema: https://compete.sparkswarm.ai/schemas/spark-compete-hotfix-v1.json
-->

```json
{
  "schema": "spark-compete-hotfix-v1",
  "event": "spark-compete-first-event",
  "team": {
    "name": "",
    "members": ["", "", ""],
    "llm_device_holder": "",
    "device_holder_github": "",
    "github_accounts": [""]
  },
  "target_repo": {
    "id": "vibeforge1111/spark-cli",
    "source": "https://github.com/vibeforge1111/spark-cli",
    "owner_surface": ""
  },
  "issue": {
    "type": "bug",
    "severity": "medium",
    "title": "",
    "actual_behavior": "",
    "expected_behavior": "",
    "repro_steps": [""],
    "affected_workflow": ""
  },
  "evidence": {
    "safe_links_only": true,
    "links": [],
    "forbidden": ["pdf", "zip", "exe", "unknown downloads", "tokens", "raw logs", "private repo maps"]
  },
  "proposed_fix": {
    "approach": "",
    "files_expected": [],
    "tests_or_smoke": ""
  },
  "pr": {
    "branch": "",
    "title_prefix": "[spark-compete]",
    "body_must_include": ["packet", "repro", "before_after_proof", "tests_or_smoke", "review_claim"],
    "url": ""
  },
  "review_claim": {
    "impact_claim": "medium",
    "evidence_types": [],
    "duplicate_notes": "",
    "risk_notes": "",
    "review_state_requested": "pr_review"
  }
}
```

## Repro

- Actual behavior:
- Expected behavior:
- Steps a reviewer can follow:

## Safe Evidence

- Before proof:
- After proof:
- Tests or smoke command:

## Scope And Risk

- Owner surface:
- Files changed:
- Security-sensitive areas touched:
- Rollback note:

## Duplicate Search

- Related issues or PRs checked:
- Why this is unique, or what new value it adds over related work:

## Contributor Checklist

- [ ] This PR is one focused fix, not a stack of unrelated fixes.
- [ ] The packet above is complete and valid JSON.
- [ ] Evidence uses screenshots, GitHub links, access-controlled docs, permissioned chat links, tests, or redacted bounded terminal excerpts only.
- [ ] No secrets, tokens, raw logs, private repo maps, raw conversations, or downloadable proof files are included.
- [ ] I actually ran the listed tests/smoke checks, or clearly stated why they were not applicable.
- [ ] Duplicate notes explain what I searched and what new value this PR adds.
- [ ] Risk notes explain security, privacy, installer, CI, dependency, prompt-injection, or other reviewer-sensitive surfaces.
