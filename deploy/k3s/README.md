# ChargePilot on k3s: Live Setup and Rebuild Notes

This document describes the ChargePilot k3s deployment for operators and AI
agents that need to rebuild or recover it. It combines the checked-in manifests
with a read-only inspection of the live cluster on 2026-10-24. Treat live
replica counts, image tags, and Argo CD revision as a dated snapshot; the
manifests and GitOps repository are the desired-state source.

For general deployment workflows, secret creation, upgrades, and safety rules,
see [the deployment guide](../../.github/instructions/DEPLOYMENT.md). Do not
copy credentials from the live cluster into this document or Git.

## Current live cluster snapshot

- Namespace: `chargepilot`.
- Cluster: one Ready k3s node, `x64-docker`, running Ubuntu 24.04.5 LTS,
  amd64, k3s/Kubernetes `v1.36.4+k3s1`, containerd `2.3.4-k3s1.36`.
- Argo CD Application: `argocd/chargepilot`; at inspection it used
  `https://github.com/jsramitgupta/ChargePilot.git`, branch `main`, path
  `deploy/k3s`; live status `Synced` / `Healthy`. The observed synced Git
  revision was `fc9eabe75338a35ab0e2270135cdbc324b825d34`. The checked-in
  Application now uses SSH; provision a read-only Argo CD deploy key before
  making the repository private. See the deployment guide.
- Istio ingress Service: `istio-system/istio-ingressgateway`, type
  `LoadBalancer`, LAN address `192.168.1.21`, ports 80 and 443 (plus status
  port 15021).
- The API, frontend, outbox relay, automation consumer, PostgreSQL, and Kafka
  were each at one ready replica when inspected.
- API-family image:
  `endusercompute/chargepilot-api:sha-d589ed504a39b18c59e534e7efba631bcd61acbe`.
  The API, relay, and consumer use this same image.
- Frontend image:
  `endusercompute/chargepilot-frontend:sha-d589ed504a39b18c59e534e7efba631bcd61acbe`.
- Data images: `postgres:16-alpine` and `apache/kafka:4.1.1`.
- The six core `chargepilot` namespace pods were Running and Ready. Kafka had
  3 restarts and PostgreSQL had 4; a recent warning event recorded a Kafka
  readiness-probe timeout. The pods were Ready at inspection time, but those
  restarts and the warning are operational signals worth checking during a
  rebuild.
- Public checks returned HTTP 200 for the management console, API health
  endpoint, and docs homepage. The docs onboarding guide also rendered
  successfully.
- The docs app, CMS, and its dedicated PostgreSQL StatefulSet are deployed in
  the separate `chargepilot-docs` namespace, each at one Ready replica. The
  docs web and CMS image tags are
  `sha-d589ed504a39b18c59e534e7efba631bcd61acbe`; the public guide API
  returned nine published guides.
- The docs PostgreSQL PVC uses node-local `local-path` storage. No independent
  backup/restore destination has been verified, and the first Strapi editor
  account has not been bootstrapped.

The Argo CD Git revision and the immutable application image tags are separate
revision identifiers. Keep both: Argo CD tracks the GitOps source; the tags
identify the built API/frontend images.

## Runtime topology

```text
Browser
  HTTPS public origins
    console-chargepilot.endusercompute.in
    api-chargepilot.endusercompute.in
        |
        v
Public DNS / edge proxy / TLS termination
        | configured origin path not verified in this snapshot
        | HTTP to Istio ingress Service port 80 (per deployment guide)
        v
Istio Gateway: chargepilot-gateway
  console host -> chargepilot-frontend:5173 (ClusterIP)
  api host     -> chargepilot-api:8000 (ClusterIP)

chargepilot-api:8000
  |-- PostgreSQL: chargepilot-postgres:5432 (ClusterIP)
  |-- Kafka: chargepilot-kafka:9092 (headless ClusterIP)
  `-- health/readiness endpoint used by dependent workers

chargepilot-outbox-relay -> PostgreSQL + Kafka + API readiness
chargepilot-automation   -> PostgreSQL + Kafka + API readiness
```

The namespace contains four Deployments and two StatefulSets. Only the API
and frontend have client-facing Services. PostgreSQL and Kafka have private
cluster Services; neither should be published through a public route,
LoadBalancer, or NodePort. The repository's Istio Gateway accepts HTTP on
port 80. Public HTTPS/TLS termination is an external edge-proxy responsibility
unless ingress TLS is explicitly configured. The ingress Service also exposes
port 443, but the ChargePilot Gateway currently declares only an HTTP listener
on port 80; the Service port alone does not establish that ChargePilot TLS is
configured. Confirm the edge-to-origin behavior separately before restoring
public traffic.

There is no site-connector workload in this namespace. Tuya device control
continues to run through separately installed site connectors on the device
LANs, which connect outbound to the ChargePilot API.

## Workloads and runtime settings

All workloads use one replica and `revisionHistoryLimit: 1`. The Deployments
run as UID/GID `10001`, non-root, with `RuntimeDefault` seccomp. Application
containers disallow privilege escalation, use a read-only root filesystem,
and drop all Linux capabilities. The API, relay, and automation containers
mount a 64 MiB `emptyDir` at `/tmp`.

| Workload | Container / command | Requests | Limits | Health / dependencies |
| --- | --- | --- | --- | --- |
| `chargepilot-api` | `api`; listens on 8000 | 250m CPU, 384Mi | 1 CPU, 1Gi | Startup/liveness `/health`; readiness `/ready`; init waits for PostgreSQL |
| `chargepilot-frontend` | `frontend`; listens on 5173 | 50m CPU, 64Mi | 250m CPU, 256Mi | Startup/liveness/readiness `/` |
| `chargepilot-outbox-relay` | `python -m app.workers outbox-relay` | 100m CPU, 128Mi | 500m CPU, 512Mi | Init waits for PostgreSQL, Kafka, and API `/ready` |
| `chargepilot-automation` | `python -m app.workers automation-consumer` | 250m CPU, 256Mi | 1 CPU, 1Gi | Init waits for PostgreSQL, Kafka, and API `/ready` |
| `chargepilot-postgres` | PostgreSQL 16 Alpine | 250m CPU, 512Mi | 1 CPU, 2Gi | `pg_isready` probes |
| `chargepilot-kafka` | Apache Kafka 4.1.1, KRaft broker/controller | 250m CPU, 768Mi | 1 CPU, 2Gi | Kafka topics-list startup/readiness probes; TCP liveness |

All four application Deployments set `CHARGEPILOT_ENVIRONMENT=production`.
The API and worker Deployments also set secure session cookies. The frontend
has the public API and frontend origins wired in its Deployment and reads the
Turnstile site key from the runtime Secret when present.

### PostgreSQL

- StatefulSet and private Service: `chargepilot-postgres`.
- One replica; database and user are both `chargepilot`.
- Port 5432; application URL uses the internal service hostname
  `chargepilot-postgres:5432`.
- Password comes from `chargepilot-runtime` key
  `CHARGEPILOT_POSTGRES_PASSWORD`.
- Claim template `data`: 20 GiB, `ReadWriteOnce`.

### Kafka

- Single KRaft broker/controller StatefulSet: `chargepilot-kafka`, node ID 1.
- Headless Service ports 9092 (PLAINTEXT broker) and 9093 (controller).
- Advertised broker: `chargepilot-kafka.chargepilot.svc.cluster.local:9092`.
- Internal PLAINTEXT only; no TLS/SASL is configured for this single-node
  in-cluster topology.
- 24 partitions by default, automatic topic creation enabled, replication
  factors set to 1.
- Claim template `data`: 10 GiB, `ReadWriteOnce`.

## Persistence and recovery constraints

Both PVCs were Bound to the `local-path` StorageClass. It is the default
`rancher.io/local-path` provisioner, with `Delete` reclaim policy, no volume
expansion, and `WaitForFirstConsumer` binding. These are node-local volumes;
they are not replicated or a backup.

This is a single-node deployment, not HA or a demonstrated large-scale
topology. Node or disk failure can make both application data stores
unavailable. No Kubernetes CronJobs or Jobs were present in the `chargepilot`
namespace at inspection time; backups outside the cluster were not checked.
Before rebuilding or replacing the node, arrange and test independent
PostgreSQL and Kafka recovery/backup procedures. Do not
delete, replace, or reinitialize existing PVCs as part of a routine app
rebuild. In particular, preserve `CHARGEPILOT_ENCRYPTION_KEY`: changing it
can make encrypted device local keys unreadable.

## Configuration and Secrets

Secrets are created out of band, are not part of the checked-in Kustomize
resources, and must not be committed or printed. The live inspection exposed
key names only, never secret values.

### `chargepilot-runtime` Secret

The live Secret contained these keys:

```text
CHARGEPILOT_ADMIN_PASSWORD
CHARGEPILOT_ADMIN_USERNAME
CHARGEPILOT_API_URL
CHARGEPILOT_DATABASE_URL
CHARGEPILOT_ENCRYPTION_KEY
CHARGEPILOT_FRONTEND_URL
CHARGEPILOT_KAFKA_BOOTSTRAP_SERVERS
CHARGEPILOT_KAFKA_SASL_MECHANISM
CHARGEPILOT_KAFKA_SASL_PASSWORD
CHARGEPILOT_KAFKA_SASL_USERNAME
CHARGEPILOT_KAFKA_SECURITY_PROTOCOL
CHARGEPILOT_KAFKA_SSL_CA_FILE
CHARGEPILOT_POSTGRES_PASSWORD
CHARGEPILOT_SECRET_KEY
CHARGEPILOT_SESSION_COOKIE_SAMESITE
CHARGEPILOT_SESSION_COOKIE_SECURE
CHARGEPILOT_TELEMETRY_CONSUMER_GROUP
CHARGEPILOT_TELEMETRY_DEAD_LETTER_TOPIC
CHARGEPILOT_TELEMETRY_KAFKA_TOPIC
CHARGEPILOT_TURNSTILE_SECRET_KEY
CHARGEPILOT_TURNSTILE_SITE_KEY
```

The API and worker Deployments load this Secret with `envFrom`. The frontend
only reads the optional Turnstile site-key entry explicitly. For the canonical
value-generation and Secret-creation procedure, follow the first-deployment
section in [the deployment guide](../../.github/instructions/DEPLOYMENT.md);
never use placeholder credentials or copy a Secret from another environment.

### `chargepilot-smtp` Secret

This optional Secret is loaded into the API container. The live Secret had:

```text
CHARGEPILOT_SMTP_FROM_EMAIL
CHARGEPILOT_SMTP_FROM_NAME
CHARGEPILOT_SMTP_HOST
CHARGEPILOT_SMTP_PASSWORD
CHARGEPILOT_SMTP_PORT
CHARGEPILOT_SMTP_USERNAME
CHARGEPILOT_SMTP_USE_SSL
CHARGEPILOT_SMTP_USE_STARTTLS
```

Recreate or update it using the SMTP instructions in
[the deployment guide](../../.github/instructions/DEPLOYMENT.md), without
replacing `chargepilot-runtime`. The optional support-recipient setting is
not present in the observed key list; application defaults apply unless an
operator deliberately configures it.

## GitOps source of truth

- Argo CD Application manifest: `deploy/argocd/chargepilot.yaml`.
- Kustomize root: `deploy/k3s/kustomization.yaml`.
- Resources: `namespace.yaml`, `datastore.yaml`, `workloads.yaml`,
  `istio.yaml`.
- Destination namespace: `chargepilot`.
- Target branch: `main`; automated sync, prune, and self-heal are enabled.
- The kustomization pins the API and frontend to immutable `sha-<commit>`
  image tags. The live tags at the snapshot date are listed above.
- Runtime and SMTP Secrets are out-of-band prerequisites, not Argo CD-managed
  resources.

Do not manually patch the shared cluster or PVCs to perform a routine app
rebuild. Merge reviewed desired-state changes to `main`, let CI and the
image-publish/GitOps workflows complete, and let Argo CD reconcile. See
[the deployment guide](../../.github/instructions/DEPLOYMENT.md) for workflow
prerequisites and the specific first-deployment process.

## Rebuild and verification checklist

For a fresh installation, follow the deployment guide rather than applying
resources blindly. The high-level dependencies are:

1. Provision a supported k3s cluster and confirm node storage capacity. This
   checked-in configuration expects one node and `local-path`; it does not
   provide HA or a storage migration.
2. Build, scan, and publish the API and frontend images through the approved
   repository workflows. Update only immutable published tags in the GitOps
   source. Do not assume old image tags remain available in a registry.
3. Create namespace `chargepilot` and out-of-band Secrets before workloads
   start. Set the database URL to the in-namespace PostgreSQL Service and
   Kafka bootstrap URL to the in-namespace Kafka Service. Generate new
   credentials for a new environment; preserve keys only when restoring the
   matching database and encrypted device state.
4. Configure public DNS/proxy routing for the frontend and API hostnames.
   Ensure HTTPS terminates at the edge and the origin connection matches the
   HTTP-only Istio Gateway, unless ingress TLS has been configured separately.
5. Install/sync the Argo CD Application and wait for all six workloads and both
   PVCs. Do not claim recovery until API readiness and external HTTPS routes
   have also been verified.
6. Restore data only from a separately verified backup and reviewed
   migration/rollback plan. Database startup `create_all()` is not a
   substitute for reviewed production schema migrations.

Read-only inspection commands (run from an authorized host with the existing
SSH configuration) are:

```bash
ssh -o BatchMode=yes rootuser@192.168.1.21 \
  'sudo -n kubectl -n chargepilot get deployments,statefulsets,pods,services,pvc -o wide'
ssh -o BatchMode=yes rootuser@192.168.1.21 \
  'sudo -n kubectl -n argocd get application chargepilot'
ssh -o BatchMode=yes rootuser@192.168.1.21 \
  'sudo -n kubectl -n chargepilot get gateways.networking.istio.io,virtualservices.networking.istio.io'
```

Do not run `kubectl get secret -o yaml`, print decoded Secret values, restart
production workloads, change image tags, or apply manifests as part of
read-only inspection. Secret key names can be inspected without displaying
values when necessary.

## Architecture limitations to retain

- PostgreSQL and Kafka are single-replica, node-local services with no
  in-cluster backup Jobs or replication observed.
- PostgreSQL is not sharded. The 10M registered / 1M active endpoint figures
  are product targets, not measured capacity claims.
- Kafka is a development/starter single-broker configuration; production
  scaling requires reviewed security, replication, and capacity work.
- API, outbox relay, and automation consumer are separate roles but share the
  same PostgreSQL schema and Kafka cluster.
- Device control is site-local: retain the separately deployed connector
  architecture and do not route cloud pods directly to Tuya LAN devices.

## Documentation site

The docs site is live at `https://docs-chargepilot.endusercompute.in` in the
separate `chargepilot-docs` namespace. The Next.js site, Strapi CMS, and
dedicated PostgreSQL StatefulSet were each Ready at the 2026-10-24 inspection.
The public homepage and onboarding guide returned HTTP 200, and the published
guide API returned nine records. Only Next.js and Strapi's read-only published
guide API are routed; the CMS admin and PostgreSQL service remain
ClusterIP-only. See [the docs-site reference](../../.github/instructions/DOCS_SITE.md)
for content ownership and release behavior.

The docs PostgreSQL PVC is node-local `local-path` storage. No independent
backup/restore path has been verified; establish and test one before relying
on this content as the sole copy. The first Strapi editor account has not been
bootstrapped. Create it through an authorized Kubernetes port-forward, never
through the public hostname. For a new environment, provision the `docs-runtime`
Secret out of band before Argo CD starts the workloads; never commit or print
its values. Use the successful CI, image-scan, and GitOps publisher workflow
for upgrades. Do not apply `docs.yaml` or set image tags by hand.

The CMS pins patched production dependencies and carries a versioned Zod 4
compatibility patch for `koa-session`. CI requires the production npm audit to
have no high or critical findings, and the image scanner remains authoritative
for published containers. Moderate dependency advisories may remain and must
be reviewed during upgrades; do not bypass either gate. The admin bootstrap
route must stay internal: create the first editor account through an
authorized Kubernetes port-forward, never through the public docs hostname.
