# R30 Installer Baseline Drift Audit

Date: 2026-06-28
Status: current-state audit, not a publication record

## Purpose

This audit checks whether R30 documentation or local installer files still claim
the old R28 installer baseline after the local and hosted baseline moved to R29.

## Current Truth

Local installer truth is R29:

- `scripts/installer-manifest.json` source release/ref:
  `spark-cli-public-installer-2026-06-26-r29`
- `scripts/install.sh` default release/ref:
  `spark-cli-public-installer-2026-06-26-r29`
- `scripts/install.ps1` default release/ref:
  `spark-cli-public-installer-2026-06-26-r29`

R30 installer pins are intentionally not published yet. R30 must not move
installer pins until owner-source commits, installed runtime heads, registry
pins, local manifest/scripts, checksums, hosted metadata, and docs agree.

## Checks Run

```bash
rg -n "R28|r28|2026-06-25-r28|2026-06-26-r29|local installer|installer manifest/scripts|hosted .*R29|hosted.*R28" docs scripts src tests -S
PYTHONPATH=src python3 -m spark_cli.cli verify --installers --json
```

Result:

- No current R30 release/prep doc claims local installer truth is R28.
- Current R28 references are historical harness/archive text or patch payload
  history, not current installer truth.
- `verify --installers --json` passed with `ok=true`.
- Local installer release pins match the committed installer manifest.
- `install.sh` and `install.ps1` match the committed checksums.

## Release Boundary

This audit does not authorize R30 installer pin movement. It only records that
the current pre-R30 baseline is R29, and that any remaining R28 wording is
historical context rather than active installer truth.
