# Spark R30 Release Note Draft

Date: 2026-06-27
Status: draft only; do not publish until R30 gates pass

## Headline

Spark R30 makes the public installer catch up with the reliability, proof, and
Telegram conversation work already proven in the running Spark stack.

## What R30 Is Meant To Ship

- Telegram streaming and rich messages default-on, with the double-preview bug fixed.
- Hidden context blocked from ordinary Telegram replies.
- Action-capable routes backed by proof capsules.
- Safe no-action prompts, including "do not run", "just explain", and "build mentioned", staying chat-only.
- Trace joins from user intent to route decision, action or no-action evidence, and reply.
- Capability evidence with last-success and last-boundary or failure proof.
- Spark replies that stay readable and human, not rigid status templates.
- Voice represented truthfully as duplex and blocker-free, while action paths remain confirmation-bound.
- Installer, registry, runtime, hosted metadata, and docs aligned to one release truth.

## What R30 Should Not Claim Yet

Do not claim R30 is published, install-green, or hosted-green until the release
packet shows:

- registry pins pass;
- source-owner handoffs have landed;
- local R30 installer verification passes;
- hosted installer verification passes after authorized deploy;
- fresh install or upgrade smoke passes on the correct lane.

## Operator Note

R30 is a reliability release, not a feature-expansion release. If a change does
not reduce a measured proof, trace-join, registry, or installer-readiness gap,
keep it out of the R30 batch.
