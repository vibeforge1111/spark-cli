# Access Level 5 Read-Only Elimination Audit - 2026-06-28

Status: active proof, not just documentation.

## Invariant

When a trusted Telegram chat moves from Access level 1, 3, or 4 to Access level
5, Spark must not merely store the chat preference. The transition is valid only
when all of these are true:

1. `spark access status --level 5 --json` reports `effective_access_level=5`.
2. Level 5 service guardrails are active for Spawner and the active Telegram
   service profile.
3. `level5.effective_codex_sandbox` is exactly `danger-full-access`.
4. The Telegram runner proves it can write a temporary state file before the chat
   is marked operator.
5. Default Codex worker launchers use the persisted Level 5 service guardrails
   even when the current parent process still has stale `read-only` or
   `workspace-write` values.
6. `level5.full_permission_proof.ok` is `true`; when the proof object is
   present, Telegram treats it as authoritative and does not fall back to older
   green-looking fields.

If any one of those is false, Spark must say Level 5 is blocked or partial; it
must not claim full operator access.

## Current Live State

Fresh local audit on 2026-06-28:

- Effective access level: `5`
- Level 5 activation state: `active_for_services`
- Service enabled: `true`
- Current shell process enabled: `false`
- Current shell Codex sandbox: `workspace-write`
- Service Codex sandbox: `danger-full-access`
- Effective Codex sandbox: `danger-full-access`
- Full permission proof: `ok=true`, `missing=[]`
- Spark workspace writable: `true`
- Service can operate whole computer: `true`
- Missing/stale services: none
- Skipped unstartable Telegram profiles: `sparkqa-bot`

The current shell not carrying Level 5 env is acceptable only because the worker
launchers read persisted module guardrails before launching Codex. A launcher that
uses stale process env directly is a release bug.

## Guardrail Coverage

- Spark CLI writes the Level 5 bundle into Spawner and every Telegram profile env:
  `SPARK_ALLOW_HIGH_AGENCY_WORKERS=1`,
  `SPARK_ALLOW_EXTERNAL_PROJECT_PATHS=1`, and
  `SPARK_CODEX_SANDBOX=danger-full-access`.
- Spark CLI requires active service restart proof before reporting Level 5 as
  effective for services.
- Telegram refuses to switch the chat to operator unless the CLI payload proves
  effective full-access sandbox and the Telegram runner write probe passes.
- Telegram now consumes `level5.full_permission_proof` directly. If that proof
  exists and is not green, the chat stays out of operator mode even if older
  compatibility fields look green.
- Telegram natural language changes such as "change my access level from one to
  five confirm" preserve the confirmation and still require fresh Level 5 proof.
- Spawner default Codex launch paths now have regression coverage proving stale
  `read-only` process env is promoted from persisted Level 5 service guardrails.

## Proof Commands

Fresh focused proof passed:

```bash
npm run test:run -- \
  src/lib/server/provider-clients/codex-cli-client.test.ts \
  src/lib/services/spark-agent-bridge.test.ts
```

Result: 22 Spawner tests passed.

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_access.py \
  -k 'level5_transition or active_for_services or service_proof'
```

Result: 5 Spark CLI tests passed, 25 deselected, 6 subtests passed.

```bash
npm test -- --run \
  tests/accessLevel5Natural.test.ts \
  tests/level5RuntimeEnv.test.ts \
  tests/accessActions.test.ts \
  tests/accessPolicy.test.ts
```

Result: Telegram Access 5, stale-env promotion, and permission-proof tests passed.

```bash
npm test -- --run tests/accessPolicy.test.ts tests/accessActions.test.ts \
  tests/profileEnv.test.ts tests/recursiveLevel5RuntimeEnv.test.ts
```

Result: 2026-06-28 focused Telegram proof passed, including CLI proof-object
adoption and stale read-only env promotion.

## Non-Bugs That Can Still Say Read-Only

- Historical mission result rows may still contain old read-only failure text.
  They are evidence history, not current capability truth.
- Intentionally read-only creator missions and diagnostic routes must remain
  read-only even under Access 5.
- A random Codex Desktop thread can still have a lower current-process sandbox.
  Spark may only claim full access for work launched through the proven Level 5
  service lane or a process that itself proves `danger-full-access`.

## Maintenance Rule

Any new Codex launch surface must add a test for this exact stale-env shape:

- persisted service env says Level 5 full access,
- current process env says `SPARK_CODEX_SANDBOX=read-only` or `workspace-write`,
- default Codex launch resolves to `--sandbox danger-full-access`,
- `level5.full_permission_proof.ok` is the authoritative full-access verdict,
- intentionally read-only commands remain intentionally read-only.
