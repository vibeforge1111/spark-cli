[spark-compete] fix(security): gate shell -c and PowerShell inline code in approval classifier

## PR Author
@trmidhi (Rayiea Hub)

## Summary
`approval_required_for_command` currently returns `action_class='none'` for inline shell execution wrappers like `bash -c ...` and PowerShell `-EncodedCommand`, allowing arbitrary command execution without an approval prompt.

This PR classifies:
- `bash/sh/zsh/fish -c/-lc` as `remote_code_execution` / **critical**
- `cmd /c` and `cmd /k` as `remote_code_execution` / **critical**
- `powershell/pwsh -Command/-EncodedCommand` (and aliases) as `remote_code_execution` / **critical**

Additionally, this PR hardens several other approval classifier gaps:
- `sudo`/`doas` privilege escalation → `identity_access_mutation` / high
- `env` with secrets → `credential_mutation` / high
- `printenv`, `set` → `credential_mutation` / high
- `gh auth token` → `credential_mutation` / critical
- `aws secretsmanager get-secret-value` / `ssm get-parameter` → `credential_mutation` / critical
- `kubectl get secret` → `credential_mutation` / critical
- `docker login` → `credential_mutation` / high
- `find -exec`/`-execdir` → `remote_code_execution` / high
- `git submodule add/update` → `remote_code_execution` / high
- Expanded external publish coverage: `twine`, `cargo`, `gem`, `nuget`, `docker push`, `pulumi`, `prisma migrate deploy`, `alembic upgrade/downgrade`, `az`/`gcloud`/`supabase` deploy, `serverless` deploy

## Actual behavior (before patch on master)
```
$ git checkout origin/master && PYTHONPATH=src python3 -c "
from spark_cli.security.approval import approval_required_for_command as a

cases = [
    (['bash','-c','echo','pwned'], 'bash -c'),
    (['sh','-lc','echo','pwned'], 'sh -lc'),
    (['cmd','/c','echo','pwned'], 'cmd /c'),
    (['powershell','-EncodedCommand','ZQ=='], 'powershell -EncodedCommand'),
    (['pwsh','-Command','Write-Output','pwned'], 'pwsh -Command'),
]
for cmd, label in cases:
    r = a(cmd)
    print(f'  {label}: requires_approval={r.requires_approval}, action_class={r.action_class}, risk={r.risk}')
"

=== BEFORE (master branch) ===

  bash -c: requires_approval=False, action_class=none, risk=none
  sh -lc: requires_approval=False, action_class=none, risk=none
  cmd /c: requires_approval=False, action_class=none, risk=none
  powershell -EncodedCommand: requires_approval=False, action_class=none, risk=none
  pwsh -Command: requires_approval=False, action_class=none, risk=none
```

All five shell inline-execution wrappers return `requires_approval=False` — no approval gate.

## Expected behavior (after patch on PR branch)
```
$ git checkout fix/approval-shell-inline-exec && PYTHONPATH=src python3 -c "
from spark_cli.security.approval import approval_required_for_command as a

cases = [
    (['bash','-c','echo','pwned'], 'bash -c'),
    (['sh','-lc','echo','pwned'], 'sh -lc'),
    (['cmd','/c','echo','pwned'], 'cmd /c'),
    (['powershell','-EncodedCommand','ZQ=='], 'powershell -EncodedCommand'),
    (['pwsh','-Command','Write-Output','pwned'], 'pwsh -Command'),
    (['zsh','-c','echo','pwned'], 'zsh -c'),
    (['fish','-c','echo','pwned'], 'fish -c'),
]
for cmd, label in cases:
    r = a(cmd)
    print(f'  {label}: requires_approval={r.requires_approval}, action_class={r.action_class}, risk={r.risk}')
"

=== AFTER (PR #490 branch) ===

  bash -c: requires_approval=True, action_class=remote_code_execution, risk=critical
  sh -lc: requires_approval=True, action_class=remote_code_execution, risk=critical
  cmd /c: requires_approval=True, action_class=remote_code_execution, risk=critical
  powershell -EncodedCommand: requires_approval=True, action_class=remote_code_execution, risk=critical
  pwsh -Command: requires_approval=True, action_class=remote_code_execution, risk=critical
  zsh -c: requires_approval=True, action_class=remote_code_execution, risk=critical
  fish -c: requires_approval=True, action_class=remote_code_execution, risk=critical
```

All shell inline-execution wrappers now return `requires_approval=True` with `remote_code_execution` / **critical**.

## Additional Security Hardening Proof
```
=== Additional Security Hardening Tests (PR #490 branch) ===

  sudo git push --force: requires_approval=True, action_class=git_history_mutation, risk=critical
  env TOKEN=xxx gh auth token: requires_approval=True, action_class=credential_mutation, risk=critical
  printenv: requires_approval=True, action_class=credential_mutation, risk=high
  aws secretsmanager get-secret-value: requires_approval=True, action_class=credential_mutation, risk=critical
  kubectl get secret: requires_approval=True, action_class=credential_mutation, risk=critical
  docker login: requires_approval=True, action_class=credential_mutation, risk=high
  find -exec: requires_approval=True, action_class=remote_code_execution, risk=high
  git submodule add: requires_approval=True, action_class=remote_code_execution, risk=high
  twine upload: requires_approval=True, action_class=external_publish, risk=high
  cargo publish: requires_approval=True, action_class=external_publish, risk=high
  pulumi up: requires_approval=True, action_class=external_publish, risk=high
  prisma migrate deploy: requires_approval=True, action_class=external_publish, risk=high
  gcloud run deploy: requires_approval=True, action_class=external_publish, risk=high
```

## Pytest Output
```
$ PYTHONPATH=src python3 -m pytest tests/test_cli.py -k "approval" -v --tb=short

tests/test_cli.py::SparkCliTests::test_approval_classifier_allows_access_guide PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_allows_access_status PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_allows_autostart_status PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_allows_harmless_status PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_allows_setup_without_autostart PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_blocks_level5_access_mutation_non_interactively PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_blocks_non_interactive_sensitive_command PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_autostart_install PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_destructive_delete PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_docker_privilege_escalation PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_git_history_mutation PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_hosted_deploy PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_hosted_secret_mutation PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_purge_home_uninstall PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_remote_script_execution PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_secret_reveal PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_secret_set PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_security_revoke_all PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_flags_setup_default_autostart PASSED
tests/test_cli.py::SparkCliTests::test_approval_classifier_hardens_secret_publish_and_wrapper_gaps PASSED [24 subtests]
tests/test_cli.py::SparkCliTests::test_approval_classify_cli_outputs_json PASSED
tests/test_cli.py::SparkCliTests::test_approval_enforcement_covers_publish_deploy_and_privileged_actions PASSED

22 passed, 30 subtests passed in 0.25s
```

**Targeted regression test** (the new test added by this PR):
```
$ PYTHONPATH=src python3 -m pytest tests/test_cli.py::SparkCliTests::test_approval_classifier_hardens_secret_publish_and_wrapper_gaps -v

tests/test_cli.py::SparkCliTests::test_approval_classifier_hardens_secret_publish_and_wrapper_gaps PASSED [100%]
1 passed, 24 subtests passed in 0.17s
```

All 22 approval-classifier tests pass with zero regressions. The new test covers 24 sub-cases including all shell wrappers, credential reveals, and expanded publish vectors.

## Duplicate Notes

| PR | Author | Title | Overlap | Resolution |
|----|--------|-------|---------|------------|
| **#301** | rifki0908 (Cutkin) | gate interpreter -c/-e inline execution | **Partial**: Both gate `bash/sh/zsh/fish -c`. PR #301 uses flat `interpreters` set with risk=**high**. PR #490 uses shell-specific dict with `-lc` support + `cmd /c /k` + PowerShell wrappers at risk=**critical**. PR #301 also covers Python/Perl/Ruby/Node interpreters (not covered here). | Compatible: PR #301's interpreter coverage and PR #490's shell/Windows coverage are complementary. If both merge, the more-specific shell check in #490 (critical) will match before #301's generic check (high). Consider merging #490 first for the higher-risk shell gates, then rebasing #301. |
| **#488** | rahmanhsim (LOLCAT) | gate dd/tee/truncate/nc/crontab/at destructive-write | **None**: PR #488 covers destructive filesystem writes and persistence primitives. PR #490 covers shell inline code execution and credential reveals. Zero diff overlap in `approval.py`. | No conflict. Both can merge independently. |
| **#431** | vibeforge1111 | security: harden approval classifier gaps | **None (already merged)**: PR #431 was merged into master on 2026-05-27. PR #490 builds on top of it, extending coverage further. | Baseline dependency. No duplicate. |

**Search methodology**: Searched open/closed PRs in `vibeforge1111/spark-cli` for keywords: `shell -c`, `inline code`, `bash`, `powershell`, `pwsh`, `cmd /c`, `approval classifier`, `approval harden`, `EncodedCommand`. Only PRs #301, #488, and #431 were relevant.

**Conclusion**: No exact duplicate exists. PR #301 has partial conceptual overlap on `bash/sh/zsh/fish -c` but differs in approach (shell-specific critical vs generic high) and scope (Windows shells + credential hardening here; interpreter coverage there). The two PRs are complementary.

## Risk Notes

### Scope
- **Primary file**: `src/spark_cli/security/approval.py` (+~176 lines, purely additive before the final fallback return)
- **Test file**: `tests/test_cli.py` (+~1 new test method with 24 sub-cases, plus supporting test infrastructure)
- **Other files touched**: 7 additional files (`pyproject.toml`, `registry.json`, `scripts/install.ps1`, `scripts/install.sh`, `scripts/installer-manifest.json`, `src/spark_cli/cli.py`, `tests/test_browser_use_cli.py`) — these appear to be unrelated installer/config changes bundled in the branch. **Only `approval.py` and `tests/test_cli.py` are relevant to the security fix.**

### Risk Assessment
1. **Purely additive**: All new checks are inserted before the final fallback `return _decision(parts, ctx, "none", "none", ...)`. No existing checks are modified or removed. This means the change is strictly more restrictive — commands that previously required approval still do; commands that previously did not may now require it.

2. **No auth/CI/installer/dependency changes**: The approval.py changes do not touch authentication, CI pipelines, installer scripts, sandbox wiring, or dependency files.

3. **Safe variants remain unblocked**: Shell commands without inline execution flags (e.g., `bash script.sh`, `powershell script.ps1`) are not affected. Only the specific inline execution flag patterns are gated.

4. **Confirmation phrases are clear**: Each new gate provides a descriptive confirmation phrase (e.g., "approve shell code execution", "approve privilege escalation", "approve environment reveal") so operators can make informed decisions.

5. **Rollback**: Revert the single commit on `fix/approval-shell-inline-exec` to restore previous behavior.

### Potential Concerns
- **Overlap with PR #301**: Both this PR and #301 gate `bash/sh/zsh/fish -c`. This PR classifies them as `critical` while #301 uses `high`. If both merge, the first check matched in execution order wins. This PR's checks appear earlier in the function, so `critical` would take precedence.
- **Branch contains unrelated changes**: The branch includes changes to `cli.py`, `install.sh`, `install.ps1`, `installer-manifest.json`, `registry.json`, and `pyproject.toml` that appear unrelated to the security fix. The maintainer may want a cleaner branch with only the approval.py + test changes.
- **`pwsh.exe` and `powershell.exe` matching**: The check uses `.exe` suffix variants which only match on Windows/Cygwin. On Linux, `pwsh` and `powershell` are the canonical names. Both variants are included for cross-platform safety.

## Spark Compete Packet
```json
{
  "schema": "spark-compete-hotfix-v1",
  "event": "spark-compete-first-event",
  "submission_mode": "public_repo_pr",
  "submission_target_url": "https://github.com/vibeforge1111/spark-cli/pull/490",
  "team": {
    "name": "Rayiea Hub",
    "members": ["driasim", "trmidhi", "yasfib"],
    "llm_device_holder": "driasim",
    "device_holder_github": "https://github.com/driasim",
    "github_accounts": ["driasim", "trmidhi", "yasfib"]
  },
  "target_repo": {
    "id": "vibeforge1111/spark-cli",
    "source": "https://github.com/vibeforge1111/spark-cli",
    "owner_surface": "spark-cli"
  },
  "issue": {
    "type": "bug",
    "severity": "critical",
    "title": "approval_required_for_command does not classify bash/sh/cmd/pwsh inline code flags (-c, /c, -EncodedCommand)",
    "actual_behavior": "bash -c / sh -lc / cmd /c / pwsh -EncodedCommand return action_class=none and requires_approval=False.",
    "expected_behavior": "These wrappers should be classified as remote_code_execution (critical) and require approval.",
    "repro_steps": [
      "PYTHONPATH=src python3 -c \"from spark_cli.security.approval import approval_required_for_command as a; r=a(['bash','-c','echo','pwned']); assert not r.requires_approval\""
    ],
    "affected_workflow": "Spark agent sandbox approval gate"
  },
  "evidence": {
    "safe_links_only": true,
    "before_after_proof": "See terminal output above: Before — all 5 shell wrappers return requires_approval=False. After — all 7 shell wrappers return requires_approval=True, remote_code_execution/critical.",
    "links": [],
    "forbidden": ["pdf","zip","exe","tokens","browser cookies","wallet material","raw logs","raw conversations","raw memory","raw patches","private repo maps","private scoring details"]
  },
  "proposed_fix": {
    "approach": "Classify inline shell execution flags as remote_code_execution/critical. Additionally harden sudo/env/printenv/credential reveals and expanded external publish coverage.",
    "files_expected": ["src/spark_cli/security/approval.py"],
    "tests_or_smoke": "22 approval tests pass, 24 new sub-cases in targeted regression test"
  }
}
```
