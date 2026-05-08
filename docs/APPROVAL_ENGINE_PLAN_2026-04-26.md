# Spark Approval Engine Plan - 2026-04-26

This is a planning document only. Do not implement the approval engine from memory; update this plan first, then cut the implementation in small, test-heavy slices.

## Goal

Add a narrow approval engine for sensitive Spark actions without making everyday Spark usage feel blocked or fragile.

The approval engine should protect operations where a wrong command can destroy user work, expose secrets, mutate identity, publish externally, or rewrite shared history. It should not interrupt normal chat, local planning, harmless reads, status checks, or ordinary app usage.

## Non-Goals

- Do not require Docker or sandboxing for normal Spark operation.
- Do not put every action behind approval.
- Do not block read-only inspection, diagnostics, or `spark status`.
- Do not make approval depend on an LLM judgment alone.
- Do not implement in one wide patch across all repos.
- Do not auto-approve because an action was requested by a model or plugin.

## Sensitive Action Classes

| Class | Examples | Default |
| --- | --- | --- |
| Destructive filesystem | Delete files/directories, overwrite non-Spark-owned files, purge local state, uninstall autostart entries | Require approval |
| Git history mutation | `git filter-repo`, rebase published branch, force-push, tag rewrite | Require approval |
| Credential mutation | Rotate, delete, export, print, or move secrets; change provider auth refs | Require approval |
| External publish | Push public code, create release, publish package, post public content, deploy hosted installer | Require approval unless already inside explicit ship flow |
| Process/autostart mutation | Install/remove Startup folder entries, Task Scheduler jobs, shell profile edits, HKCU PATH writes | Require approval |
| Network exfiltration risk | Upload logs, attach raw state DB, send local files to a provider | Require approval |
| Identity/access mutation | Change Telegram admin IDs, pairing links, channel allowlists, operator scopes | Require approval |
| High-cost execution | Long-running autoloop, bulk LLM job, large benchmark, paid-provider fanout | Require budget approval |

## Allowed Without Approval

- Read-only status, health, version, config-summary, and diagnose commands that redact secrets.
- Local code search and static analysis.
- Focused tests.
- Writing Spark-owned generated files when inside the configured safe root and not through symlinks/reparse points.
- Report-only verification such as `spark verify --provenance`.
- Dry runs that do not mutate state.

## Approval Decision Model

Every candidate action should resolve to a structured decision before execution:

```json
{
  "action_id": "delete-local-temp-home",
  "class": "destructive_filesystem",
  "risk": "high",
  "target": "C:/Users/USER/Desktop/spark-intelligence-builder/.tmp-home-live-telegram-real",
  "reason": "Delete ignored temp runtime home after secret scan",
  "requires_approval": true,
  "approval_mode": "interactive",
  "expires_at": "2026-04-26T22:30:00Z"
}
```

Rules:

- Classification must be deterministic code, not LLM prose.
- The engine must show the exact target and action class.
- Approval must be scoped to one action or a small explicit batch.
- Approval should expire quickly.
- Denial must be safe and leave state unchanged.
- Approvals must be logged without secret values.

## User Experience Shape

For sensitive actions, Spark should present a concise prompt:

```text
Approval required: delete ignored Builder temp homes
Risk: destructive filesystem
Targets:
- <builder-workspace>\.tmp-home-live-telegram-real
- <builder-workspace>\.tmp-home-poll-real

Type the confirmation phrase to continue:
delete builder temp homes
```

For less risky but still sensitive actions, a yes/no confirmation is enough. For destructive, credential, force-push, and publish actions, require a short confirmation phrase derived from the target.

## Data Model

Start with local JSONL audit records under Spark home:

```text
~/.spark/security/approvals.jsonl
```

Suggested fields:

- `approval_id`
- `created_at`
- `expires_at`
- `actor`
- `surface`
- `action_class`
- `risk`
- `target_digest`
- `target_display`
- `reason`
- `decision`: `approved`, `denied`, `expired`, `skipped`
- `command_digest`
- `result`: `not_run`, `succeeded`, `failed`

Never store raw secret values, full env dumps, raw file contents, or full command payloads that include credentials.

## Architecture

Add a small approval package in `spark-cli` first:

```text
src/spark_cli/security/approval.py
```

Core functions:

- `classify_action(action: ApprovalAction) -> ApprovalDecision`
- `require_approval(decision: ApprovalDecision, prompt: ApprovalPrompt) -> ApprovalGrant`
- `record_approval_event(event: ApprovalEvent) -> None`
- `approval_required_for_command(argv: list[str], context: CommandContext) -> ApprovalDecision`

The first implementation should be local-only and CLI-only. Other repos can integrate after the CLI contract is stable.

## Rollout Phases

### Phase 0 - Documentation Only

Status: this document.

- Define action classes.
- Define approval UX.
- Define audit record shape.
- Identify first integration points.

### Phase 1 - Report-Only Classifier

- Add classifier and tests.
- Add `spark approval classify --json -- <command>`.
- Do not block execution.
- Add fixtures for delete, force-push, credential export, hosted deploy, and harmless status.

### Phase 2 - CLI Gating For Narrow Commands

Gate only:

- `spark uninstall`
- `spark purge`
- history rewrite helpers if added
- local temp cleanup helper if added
- secret export/delete commands

Keep normal setup/start/status/install flows unchanged unless they hit a sensitive class.

### Phase 3 - Cross-Repo Call Sites

Integrate only after Phase 2 is stable:

- `spark-telegram-bot`: destructive local state reset, webhook ownership mutation.
- `spark-intelligence-builder`: pairing identity mutation, channel allowlist mutation, temp-home cleanup.
- `domain-chip-memory`: cryptographic purge / hard forget.
- `spark-agent-site`: hosted installer deploy/publish.

### Phase 4 - Policy Profiles

Add optional profiles:

- `solo-dev`: fewer prompts for local Spark-owned paths.
- `production`: strict prompts for autostart, publish, identity, and credential actions.
- `ci`: non-interactive deny by default unless explicit signed approval token exists.

## First Integration Points

1. `spark uninstall`: approval for removing autostart entries, PATH entries, and Spark home.
2. Secret commands: approval for delete/export/reveal operations.
3. Any future `spark cleanup temp-homes`: approval before deleting ignored temp dirs.
4. Any future history scrub helper: approval before `git filter-repo` or force-push guidance.
5. Hosted installer deploy helper: approval before publish/deploy.

## Test Requirements

Minimum tests before enforcement:

- Harmless commands do not require approval.
- Destructive commands require approval and include exact target display.
- Confirmation phrase mismatch denies execution.
- Expired approval denies execution.
- Approval logs redact secret-like strings.
- Batch approval cannot silently include targets not shown in the prompt.
- Non-interactive mode fails closed for high-risk classes.
- Windows paths, symlinks, reparse points, and Spark safe-root boundaries are covered.

## Open Questions

- Should approvals be per command, per target, or per action class plus target digest?
- Should approval grants survive process restart? Default recommendation: no for high-risk actions.
- How should Telegram-sourced approvals work, if at all? Default recommendation: do not allow remote chat approval for local destructive actions until identity binding is stronger.
- Should approvals require OS authentication for credential export? Default recommendation: yes later, but not in Phase 1.

## Implementation Guardrails

- Keep the first patch report-only.
- Keep enforcement local to `spark-cli` before other repos integrate.
- Add tests before each command is gated.
- Avoid broad wrappers around all subprocess execution; gate explicit sensitive operations at their intent boundary.
- Never ask the model to decide whether approval is required.
- Never store secrets in approval logs.
