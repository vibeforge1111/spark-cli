# Optional Docker Workbench

Last updated: 2026-05-10

Docker is optional Spark infrastructure. It is useful for clean testing and future sandbox experiments, but Spark setup, Telegram, Builder, Memory, Character, and normal local runtime flows must continue to work without Docker.

## What This Is

This repo provides two opt-in Docker lanes:

| Lane | Path | Purpose | Network default |
|---|---|---|---|
| Dev smoke | `docker/dev/Dockerfile` | Clean disposable environment for tests and installer verification | On |
| Sandbox run | `docker/sandbox/Dockerfile` | Restricted CLI command experiments with no real home or secrets | Off |
| Live image smoke | `docker/live/Dockerfile` | Hosted Spark Live image build and entrypoint guard checks | Hosted env only |

Use these when you want to test a new feature without contaminating the operator's real `~/.spark` state.

SSH and Modal are separate future lanes, not replacements for this Docker
workbench:

- [Agentic remote sandbox security research](./AGENTIC_REMOTE_SANDBOX_SECURITY_RESEARCH.md)
  is the shared threat model and control set for Docker, SSH, Modal, Railway,
  and future VPS execution lanes.
- [OWASP agentic security deep dive](./OWASP_AGENTIC_SECURITY_DEEP_DIVE.md)
  maps OWASP ASI, LLM, MCP, and Agentic Skills risks to Spark controls.
- [Remote sandbox security checklist](./REMOTE_SANDBOX_SECURITY_CHECKLIST.md)
  is the PR gate before any remote execution or hosted sandbox work ships.
- [SSH remote sandbox architecture](./SSH_REMOTE_SANDBOX_ARCHITECTURE.md) covers
  user-owned VPS/GPU/home-server compatibility. SSH is transport, not a sandbox,
  so the plan starts with doctor and smoke commands before deploys.
- [Modal sandbox architecture](./MODAL_SANDBOX_ARCHITECTURE.md) covers
  ephemeral cloud sandboxes for disposable execution. Modal comes after SSH in
  the rollout order.

## What This Is Not

Docker is not:

- a required Spark dependency;
- required for `spark setup`;
- required for Telegram or Spawner;
- required for normal memory or personality flows;
- a replacement for real host verification before a release;
- a guarantee that arbitrary hostile code is safe.

The sandbox lane reduces blast radius for experiments. It is not a full adversarial security boundary.

## Dev Smoke Lane

Use this for clean regression checks:

```powershell
.\scripts\docker-dev-smoke.ps1
```

```bash
bash scripts/docker-dev-smoke.sh
```

By default this builds `spark-cli-dev:local` and runs:

```bash
python -m pytest tests/test_cli.py -q
python -m spark_cli.cli verify --installers
```

Optional registry/provenance checks:

```powershell
.\scripts\docker-dev-smoke.ps1 -RegistryPins -Provenance
```

```bash
SPARK_DOCKER_REGISTRY_PINS=1 SPARK_DOCKER_PROVENANCE=1 bash scripts/docker-dev-smoke.sh
```

Use a custom command:

```powershell
.\scripts\docker-dev-smoke.ps1 -Command "spark --help"
```

```bash
SPARK_DOCKER_DEV_CMD="spark --help" bash scripts/docker-dev-smoke.sh
```

## Sandbox Lane

Use this for low-trust CLI experiments:

```powershell
python -m spark_cli.cli sandbox docker doctor --json
python -m spark_cli.cli sandbox docker smoke --json
```

```bash
spark sandbox docker doctor --json
spark sandbox docker smoke --json
```

The smoke command builds the sandbox image if needed, then runs `spark status
--help` with network off, no real Spark secrets, a read-only root filesystem,
all Linux capabilities dropped, and only tmpfs scratch space.

By default the sandbox lane does not bind-mount the operator's home, current
workspace, Spark home, or Docker socket. The Spark CLI checkout is copied into
the image at build time, and writable state is limited to container tmpfs paths
such as `/tmp`, `/sandbox/home`, and `/sandbox/spark-home`.

```powershell
.\scripts\docker-sandbox-run.ps1 status --help
```

```bash
bash scripts/docker-sandbox-run.sh status --help
```

The wrapper runs the container with:

- `--network none`
- `--read-only`
- `--cap-drop ALL`
- `--security-opt no-new-privileges`
- tmpfs scratch space at `/tmp` and `/sandbox`
- isolated `HOME` and `SPARK_HOME`

To allow network for a specific experiment:

```powershell
.\scripts\docker-sandbox-run.ps1 -Network verify --installers
```

```bash
SPARK_DOCKER_SANDBOX_NETWORK=bridge bash scripts/docker-sandbox-run.sh verify --installers
```

Network-on sandbox runs should be treated as a separate risk decision.

## Optional GitHub Workflow

The manual workflow at `.github/workflows/docker-optional.yml` builds the dev,
sandbox, and live images and runs bounded smoke commands. It only runs through
`workflow_dispatch`, so Docker does not become a required CI dependency.

## Secret Rules

- Do not mount the real `~/.spark` into these containers.
- Do not pass production secrets unless the test is explicitly about secret plumbing.
- Prefer fake env vars, test bot tokens, or local throwaway homes.
- If a real secret is passed into a container and printed, copied, logged, or committed, rotate it.

## Future Approval-Engine Tie-In

Later, the approval engine can route sensitive actions into this optional sandbox lane. Good candidates:

- deletion tests;
- risky module install experiments;
- generated command dry-runs;
- migration rehearsals;
- untrusted plugin/module validation.

The approval engine should stay policy-first. Docker can be one execution backend, not the policy itself.

## Maintainer Checklist

When changing Docker workbench files:

1. Keep Docker optional in docs and workflows.
2. Avoid mounting real user homes by default.
3. Keep sandbox network off by default.
4. Keep sandbox root filesystem read-only.
5. Run the manual optional Docker workflow when Docker behavior changes.
6. Do not add Docker to normal install requirements.
