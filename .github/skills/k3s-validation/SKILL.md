---
name: k3s-validation
description: "Use when validating ChargePilot changes on Linux, Docker, Kubernetes, or the authorized k3s cluster, including local-development integration checks and post-deployment image verification."
---

# ChargePilot k3s Validation

Use the authorized Linux host for realistic Linux, Docker, and k3s validation
when local checks do not cover the behavior. The cluster is shared deployed
infrastructure, not a disposable development cluster.

## Host and safety boundaries

- Host: `rootuser@192.168.1.21`
- Connect with the existing SSH configuration/key; never store credentials in
  the repository or print secrets from the host.
- Read `.github/instructions/DEPLOYMENT.md` before remote operations.
- Prefer read-only `kubectl get`, `describe`, `logs`, rollout status, and
  Docker inspection.
- Do not change workloads, persistent data, or cluster configuration unless
  the user explicitly requests that specific operation.
- Never use production data for test fixtures or destructive tests.

## Development and deployment procedure

1. Run the smallest relevant local tests and builds first.
2. Use SSH with non-interactive existing credentials for a bounded remote
   check. The configured kubeconfig may require `sudo -n kubectl`.
3. For integration validation, inspect namespace, workload readiness, pod
   status, and the exact image tags before and after a test. Avoid making
   changes to shared workloads for ad-hoc experiments.
4. For a requested application deployment, push the approved change to
   `main` and let the successful CI run trigger the repository's image publish
   and GitOps manifest update workflow. Do not manually change image tags or
   apply manifests unless explicitly requested.
5. Verify the GitHub Actions results, GitOps manifest source-SHA tags, k3s
   rollout status, deployed image tags, and ready pods. Report any delay or
   failure without claiming deployment success.

Example read-only checks:

```sh
ssh -o BatchMode=yes rootuser@192.168.1.21 \
  'sudo -n kubectl get deployments -A -o wide'
ssh -o BatchMode=yes rootuser@192.168.1.21 \
  'sudo -n kubectl get pods -A -o wide'
```
