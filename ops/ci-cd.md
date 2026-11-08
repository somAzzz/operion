# CI and gateway delivery

[Verify](../.github/workflows/verify.yml) runs on every push, pull request, and manual
dispatch. The source remains English. This pipeline delivers the existing read-only
WWI gateway; it does not enable business writes or establish E5 production acceptance.

## Checks and image publication

| Job | Required result |
| --- | --- |
| Repository policy | English-only scan and rejection tests, actionlint 1.7.11, shell syntax, whitespace check |
| Python | Locked Python 3.12 dependencies, Ruff, offline suite, developer case evidence, isolated PostgreSQL tests |
| Web | Node 22, locked npm installation, TypeScript, session/navigation tests, webpack production build, production rendering tests |
| Gateway images (agent/web) | Both Dockerfiles build only after all preceding jobs pass |

Only runs on `main` outside pull requests publish images. Other branches and pull
requests build images without registry login or publication. Published image names are
`ghcr.io/<lowercase-owner>/<lowercase-repository>-agent:sha-<full-commit-sha>` and
the corresponding `-web` name. No mutable `latest` tag is produced. Each service
uploads an image record with its commit, service name, and immutable digest. The
two `gateway-image-*` artifacts expire after 30 days; developer evidence after 14.

The build jobs use the repository `GITHUB_TOKEN` with `packages: write`; ordinary
checks receive only `contents: read`. No registry password or business credential
is needed for CI. Ensure repository/organization policy allows GitHub Actions,
the referenced actions, and package publication. For pre-existing packages, grant
this repository Actions access to those packages.

Protect `main` against direct changes and require `Repository policy`, `python`,
`web`, `Gateway images (agent)`, and `Gateway images (web)` before merging. These
repository settings must be configured by an administrator; a workflow file cannot
enable them.

## English-only scope

Run `scripts/verify.sh english` with Python 3 and Git; the offline entry point runs
the same check. The scanner examines Git-tracked and new non-ignored files,
including documentation, prompts, code, configuration, tests, and test fixtures.
It rejects Han characters in content or file names, Unicode escape forms used by
Python/JSON/JavaScript (including surrogate pairs), and invalid UTF-8 text. A failure
returns nonzero and emits GitHub file/line annotations without printing source text.

Binary asset extensions and dependency lockfiles are excluded. The top-level
`data/` and `reports/` trees contain source snapshots and generated evidence and
are excluded except their `README.md` files. Ignored histories, dependencies, and
credentials are not scanned. This is a Han-character policy, not a general natural
language classifier, and it does not rewrite business data or historical conversations.

## One-time deployment host setup

1. Initialize the gateway using the [gateway runbook](auth-gateway.md) and configure
   a running Collector using the [telemetry runbook](../docs/enterprise/opentelemetry-langfuse-runbook.md).
   Keep its existing identity policy, certificates, named volumes, and credentials.
   The model remains an existing SGLang service on host port 30000.
2. Register a dedicated Linux x64 self-hosted runner on that same Docker host,
   labeled `operion-gateway`. It needs Python 3.12, Git, Bash, grep, Docker, and
   Docker Compose with access to the existing `operion-gateway` project. Use a
   dedicated runner account that can read the gateway state and telemetry env file.
   Do not use it for untrusted pull requests or grant it access to business systems.
3. Create the GitHub environment `gateway`. Restrict deployment branches to `main`
   and configure required reviewers where supported by the repository plan.
   Only the deployment job uses this runner and environment.
4. Set these **environment variables** in `gateway` to existing absolute host paths:

   | Variable | Example |
   | --- | --- |
   | `OPERION_GATEWAY_ENV_FILE` | `/srv/operion/.env.langfuse.local` |
   | `OPERION_GATEWAY_RUNTIME_DIR` | `/srv/operion/var/gateway` |

   Env-file contents and gateway secrets remain on the host. Do not paste them
   into workflow YAML, logs, artifacts, or repository variables. The runtime
   directory must contain `tls/ca.crt` and `policy/identity-policy.json`.

Do not place persistent gateway state inside the runner's checkout, which
`actions/checkout` may clean. Existing local Compose commands keep their original
relative runtime paths when `OPERION_GATEWAY_RUNTIME_DIR` is unset.

## Manual deployment and recovery

In GitHub Actions, choose **Verify → Run workflow → main**, enable
**Deploy the verified images to the existing gateway**, and dispatch. The workflow
reruns every check, builds and publishes both images, then reaches the protected
`gateway` environment. A plain push never deploys. Selecting another branch never
publishes or deploys, even when the deployment input is enabled.

The deployment downloads only image records from its own run, checks that both
belong to the exact checked-out commit and this repository, and accepts only
`ghcr.io` digest references. It uses those images with `--no-build`, retains
the existing telemetry settings, and sets `OPERION_RELEASE_ID` to the commit SHA.
It pulls both images before updating either service, updates only Agent/Web with
`--no-deps`, and waits for their health checks. It refuses deployment if tracing
is disabled, the OTLP endpoint differs from the gateway Collector, or the Collector
is stopped. Identity infrastructure and volumes are not recreated.

Inspect the Actions job, Compose health, release labels, and telemetry after a
deployment. Health checks do not prove model routing, TLS/OIDC login, or full user
task completion; retain the [gateway acceptance checks](auth-gateway.md#4-reproducible-acceptance)
and read-only real-model acceptance before a release is accepted.

If pulling fails, the running services are unchanged. An update or health failure
fails the job and may leave one service updated; there is no automatic rollback
or retry. Retain the previous commit and its two digest records. For rollback,
use a separate clean checkout at that exact previous revision and run:

```bash
python3 scripts/deploy_gateway_release.py \
  --manifest-dir /secure/path/to/previous-image-records \
  --repository owner/repository \
  --revision <previous-full-commit-sha> \
  --env-file /srv/operion/.env.langfuse.local \
  --runtime-dir /srv/operion/var/gateway \
  --check
```

Authenticate Docker to GHCR with package-read permission first. After reviewing
the preflight result, rerun without `--check`. The same telemetry, digest, and
health checks apply. Preserve identity/conversation volumes; do not use
`docker compose down --volumes` as a release or recovery step.

## Local verification

```bash
scripts/verify.sh english
scripts/verify.sh offline
scripts/verify.sh case
scripts/verify.sh postgres
scripts/verify.sh web
docker run --rm -v "$PWD:/repo:ro" -w /repo rhysd/actionlint:1.7.11 -color
docker build -f deploy/gateway/agent.Dockerfile -t operion-ci-check-agent:local .
docker build -t operion-ci-check-web:local apps/web
```

Repository configuration is distinct from an executed remote release. Publishing
requires pushing this workflow to GitHub; deployment also requires the environment
and runner setup above. Neither is implied by local checks passing.
