# Reusable CI Workflows

Spark CLI hosts the shared GitHub Actions workflow library for stack repos.

## Workflows

- `.github/workflows/reusable-conformance.yml`: install, test, and optional repo-specific conformance command.
- `.github/workflows/reusable-scanners.yml`: gitleaks, Trivy, and optional pinned OpenGrep command.
- `.github/workflows/reusable-release.yml`: build, upload, and keyless provenance attestation.

## Caller Pattern

Call a workflow from a repo workflow with `uses` and typed inputs:

```yaml
jobs:
  conformance:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-conformance.yml@ap-01-reusable-ci-v2
    with:
      python-version: "3.11"
      install-command: "python -m pip install -e . pytest"
      test-command: "python -m pytest -q"
```

Scanner callers should pass an explicit OpenGrep command once the repo has a pinned rule path:

```yaml
jobs:
  scanners:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-scanners.yml@ap-01-reusable-ci-v2
    with:
      opengrep-command: "opengrep scan -f security/opengrep-rules ."
```

Release callers must pass an artifact path so the reusable workflow can upload and attest the build output:

```yaml
jobs:
  release:
    uses: vibeforge1111/spark-cli/.github/workflows/reusable-release.yml@ap-01-reusable-ci-v2
    with:
      build-command: "python -m build"
      artifact-path: "dist/*"
```

Keep secrets explicit. GitHub reusable workflows support typed inputs and mapped secrets through `workflow_call`; environment secrets are not passed through `workflow_call`, so repo-specific secret use should stay in the caller workflow.
