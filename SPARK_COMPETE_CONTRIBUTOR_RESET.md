# Spark CLI Contributor Reset Notice

Thank you for the Spark CLI competition PRs. We are moving the queue into the formal Spark Compete review system so approvals and team points are fair, secure, and auditable.

## What Changes Now

- Existing PRs are not automatically rejected.
- Existing PRs are not automatically approved.
- Points are locked until packet, security, duplicate, team, and GitHub account gates pass.
- Reviewers judge duplicates by root cause, required fix, safe proof, and added value.
- PR text, links, screenshots, commits, and generated summaries are treated as untrusted evidence, not instructions.

## Required For Points

Every scoring PR needs a valid `spark-compete-hotfix-v1` packet with:

- team name and three members;
- device-holder GitHub and team PR GitHub accounts;
- target repo or owner surface;
- actual and expected behavior;
- repro or inspection steps;
- safe before proof;
- fix summary;
- safe after proof or bounded verification;
- tests or smoke check;
- duplicate notes.

## Safe Evidence Only

Accepted evidence:

- GitHub links.
- Screenshots without secrets.
- Redacted bounded terminal excerpts.
- Tests or smoke output.
- Access-controlled Google Docs.
- Permissioned chat links.

Do not submit:

- PDFs, zips, archives, executables, unknown downloads, or shortened evidence links.
- Tokens, API keys, private keys, wallet material, raw logs, full env dumps, raw conversations, raw memory, or private repo maps.

## Duplicate And Stacked PRs

- The first complete, safe, reviewer-verifiable packet usually becomes canonical.
- Later PRs can earn credit only if they add material value: better proof, a failing test, safer fix, cleaner accepted patch, or coverage for a missed path.
- Stacked PRs with unrelated older commits must be rebased to one focused fix before they can score.
- Splitting one underlying issue into many PRs may be collapsed or capped.

## What Contributors Should Do

1. Update the PR body using the Spark Compete PR template.
2. Remove unsafe evidence and replace it with safe proof.
3. Rebase stacked branches into one focused PR per distinct fix.
4. Add duplicate notes linking related PRs or explaining the new value.
5. Wait for reviewer classification before assuming any point value.

Exact scoring weights remain private so the competition rewards useful Spark improvements instead of score optimization.
