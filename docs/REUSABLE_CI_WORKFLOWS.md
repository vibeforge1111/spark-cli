# Reusable CI Workflows

Spark CLI hosts the shared GitHub Actions workflow library for stack repos.

## Workflows

- `.github/workflows/reusable-conformance.yml`: install, test, and optional repo-specific conformance command.
- `.github/workflows/reusable-scanners.yml`: gitleaks, Trivy, and optional pinned OpenGrep command.
- `.github/workflows/reusable-release.yml`: build, upload, and keyless provenance attestation.
- `.github/workflows/reusable-chip-publish.yml`: publish-time chip gates for schema validation, semver tag format, scanners, release artifacts, and provenance attestation.

## Caller Pattern

Call a workflow from a repo workflow with `uses` and typed inputs:

```yaml
jobs:
  conformance:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-conformance.yml@ap-01-reusable-ci-v5
    with:
      python-version: "3.11"
      install-command: "python -m pip install -e . pytest"
      test-command: "python -m pytest -q"
```

Scanner callers should pass an explicit OpenGrep command once the repo has a pinned rule path:

```yaml
jobs:
  scanners:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-scanners.yml@ap-01-reusable-ci-v5
    with:
      opengrep-command: "opengrep scan -f security/opengrep-rules ."
```

Release callers must pass an artifact path so the reusable workflow can upload and attest the build output:

```yaml
jobs:
  release:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-release.yml@ap-01-reusable-ci-v5
    with:
      build-command: "python -m build"
      artifact-path: "dist/*"
```

Chip publish callers should use the stricter publish workflow for release tags and manual release dry runs:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
  security-events: write

jobs:
  chip-publish:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-chip-publish.yml@ap-22-chip-publish-v1
    with:
      schemafile: "https://raw.githubusercontent.com/vibeforge1111/spark-domain-chip-labs/main/docs/creator_system/schemas/spark-chip.v2.schema.json"
      release-tag: "v0.1.0"
      install-command: "python -m pip install -e . pytest"
      test-command: "python -m pytest -q"
      opengrep-command: "curl -fsSL https://raw.githubusercontent.com/opengrep/opengrep/main/install.sh | bash && opengrep scan -f security/opengrep-rules ."
      build-command: "mkdir -p release-artifacts && cp spark-chip.json release-artifacts/spark-chip.json"
      artifact-path: "release-artifacts/*"
```

The caller must grant `id-token: write`, `contents: read`, and `attestations: write` because GitHub requires attestation permissions on both sides when a reusable workflow generates provenance.

Keep secrets explicit. GitHub reusable workflows support typed inputs and mapped secrets through `workflow_call`; environment secrets are not passed through `workflow_call`, so repo-specific secret use should stay in the caller workflow.
