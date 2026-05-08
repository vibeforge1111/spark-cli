# Future Installer Sandbox Options

Last updated: 2026-05-08

Status: design note only. The initial Spark installer does not configure SSH,
Modal, Railway, or VPS sandboxes yet.

## Goal

When Spark later adds sandbox onboarding to the initial installer, it should
increase compatibility without making first-run setup scary. The installer must
stay local-first and safe-by-default.

The default answer should be:

```text
No remote sandbox yet. Finish local Spark setup first.
```

SSH, Modal, and Railway/VPS options should be opt-in follow-up steps, not
required launch blockers.

## Installer UX Shape

Future prompt:

```text
Optional remote sandbox setup

Spark can later use a remote sandbox for hosted builds, user-owned servers, or
clean cloud smoke tests. You can skip this now and add one anytime.

1. Skip for now (recommended)
2. Add SSH target
3. Check Modal account
4. Open Railway/VPS hosted Spark Live checklist
```

Recommended default: `Skip for now`.

Why: new users should get a working local Spark before connecting cloud or SSH
surfaces.

## What Each Option May Do

### Skip For Now

Allowed:

- install Spark locally
- run local verification
- show the command to add sandboxes later

Not allowed:

- nag the user again during the same setup unless they ask

### Add SSH Target

Allowed:

- ask for target name, host, user, port, and identity-file path
- validate the identity file exists
- store only the key path, never key contents
- run `spark sandbox ssh doctor <name> --json`
- offer `spark sandbox ssh trust <name>` as a separate explicit step

Not allowed during initial install:

- arbitrary remote command
- deploy
- remote log tail
- root-user default
- disabling host-key checking
- copying `~/.spark`, `.ssh`, cloud config, or browser profiles

### Check Modal Account

Allowed:

- run `spark sandbox modal doctor --json`
- explain how to run Modal's official auth setup if missing
- offer no-secret smoke only after doctor passes

Not allowed during initial install:

- passing Spark provider keys
- mounting project folders
- persistent volumes
- artifact pull
- long-running paid jobs

### Railway/VPS Hosted Spark Live Checklist

Allowed:

- open or print the docs checklist
- explain split-service Spark Live shape
- list required environment variables by name only
- point to `scripts/railway-production-smoke.ps1`

Not allowed during initial install:

- collecting Railway tokens
- deploying automatically
- writing production environment variables
- claiming production is healthy without `/diagnose`, Spawner, and smoke checks

## Future Commands

Do not implement these until the current doctor/smoke lanes have more runtime
history:

```bash
spark setup --with-sandbox ssh
spark setup --with-sandbox modal
spark sandbox setup
spark sandbox ssh prepare <name> --dry-run
spark sandbox modal run --risk-reviewed ...
```

Before any of these ship, add:

- dry-run output
- audit event schema
- explicit approval prompts for paid/cloud/remote actions
- tests for secret redaction and no ambient env inheritance
- docs showing how to undo or remove each sandbox

## Acceptance Criteria Before Shipping Installer Options

- `spark verify --sandboxes --json` is green on a clean install with no targets.
- SSH add/trust/doctor/smoke has passing tests on Windows and Linux.
- Modal doctor/smoke has no-secret tests and clear auth-missing output.
- Support bundle redacts target paths, key paths, URLs with credentials, tokens,
  and private network context.
- Initial installer still succeeds when users skip every sandbox option.
- The installer never asks for private key contents, provider keys, or cloud
  deployment tokens directly.
- The user can remove any configured sandbox with a documented command.

## Copy For Spark Agents

Use this phrasing until installer support ships:

> SSH and Modal are not part of the initial installer yet. Install Spark first,
> then run `spark verify --sandboxes --json`. If you need your own server, use
> the SSH doctor/smoke path. If you need disposable cloud execution, use Modal
> doctor/smoke. Both are opt-in and no-secret by default.
