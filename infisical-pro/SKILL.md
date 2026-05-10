---
name: infisical-pro
description: Use when integrating Infisical secret management — debugging CLI errors (401, "not yet connected this project"), choosing auth methods (Service Tokens vs Machine Identities), wiring secrets into systemd/OpenClaw, installing the Infisical Operator on Kubernetes, writing InfisicalSecret CRDs, rotating DB passwords behind auto-reload, or hardening core infra (Postgres, Infisical itself) against plaintext credentials.
---

# Infisical Pro

Expert guidance on integrating Infisical secret management — both via the CLI/scripts (systemd, OpenClaw exec provider) and via the Kubernetes Operator (InfisicalSecret CRD). Two deployment styles, one set of conventions.

## Quick Reference

| Situation | Use |
|-----------|-----|
| Linux host / systemd / one-shot script | CLI + Service Token |
| OpenClaw secret backend | exec provider wrapper script |
| Kubernetes workload | Infisical Operator + InfisicalSecret CRD |
| Need TPM-bound or IP-restricted auth | Machine Identity (Universal Auth) |
| Hardening Postgres/Infisical itself | Manual K8s Secret — never the operator |

## When NOT to Use

- Stuffing application code with the Infisical SDK when the Operator can sync to a plain K8s Secret. Let the platform do it.
- The Operator for Infisical's *own* Postgres or Infisical core (circular dependency — see "Hardening Core Infrastructure" below).

## Authentication

### Service Tokens (golden path for scripts)
Stateless, no `login` step. CLI flag: `--token=$INFISICAL_TOKEN`. Best for systemd, cron, simple automation.

### Machine Identities (Universal Auth)
Used by the K8s Operator and any environment needing TPM/IP scoping. The K8s Operator expects credentials in a Secret with **camelCase** keys: `clientId` and `clientSecret` (snake_case silently fails auth).

CLI `login` for Universal Auth can fail in non-interactive sessions (e.g. `systemd --user`) due to state/permission issues — prefer Service Tokens for CLI use unless you specifically need MI.

## CLI / Script Integration

### OpenClaw exec provider — JSON stdin/stdout
OpenClaw's `exec` provider speaks JSON, not CLI args.

- stdin: `{ "protocolVersion": 1, "provider": "infisical", "ids": ["KEY1", "KEY2"] }`
- stdout: `{ "protocolVersion": 1, "values": { "KEY1": "val1" }, "errors": { "KEY2": { "message": "..." } } }`

```bash
#!/bin/bash
# OpenClaw exec provider for Infisical — JSON stdin/stdout protocol
INFISICAL_TOKEN="st.xxxx.yyyy.zzzz"
INFISICAL_API_URL="http://your-infisical-instance"

input=$(cat)
ids=$(echo "$input" | jq -r '.ids[]')
values="{}"; errors="{}"

while IFS= read -r id; do
  value=$(/usr/bin/infisical secrets get "$id" \
    --token="$INFISICAL_TOKEN" --plain --silent \
    --domain "$INFISICAL_API_URL" 2>/dev/null)
  if [ -n "$value" ]; then
    values=$(echo "$values" | jq --arg k "$id" --arg v "$value" '. + {($k): $v}')
  else
    errors=$(echo "$errors" | jq --arg k "$id" '. + {($k): {"message": "not found or empty"}}')
  fi
done <<< "$ids"

jq -n --argjson v "$values" --argjson e "$errors" \
  '{"protocolVersion": 1, "values": $v} + (if ($e | length) > 0 then {"errors": $e} else {} end)'
```

Requires `jq`. The `ref:provider:id` string format used in some docs is **not valid** in `openclaw.json` — use the JSON SecretRef object: `{ "source": "exec", "provider": "infisical", "id": "KEY_NAME" }`.

## Kubernetes Operator Integration

### Install (one-time per cluster)
```bash
helm repo add infisical-helm-charts 'https://dl.cloudsmith.io/public/infisical/helm-charts/helm/charts/'
helm repo update
kubectl create namespace infisical-operator
helm install infisical-operator infisical-helm-charts/secrets-operator --namespace infisical-operator
```

### Per-namespace auth
**Universal Auth (Machine Identities):** Every consumer namespace needs an `infisical-auth-token` Secret with `clientId` / `clientSecret` (camelCase).

**Service Token auth:** Every consumer namespace needs a Secret with key `infisicalToken`. The token must be scoped to `/**` (not just `/`) for the InfisicalSecret CRD's `secretsPath` field to work. A token scoped to `/` always returns root secrets regardless of what `secretsPath` you specify in the CRD.

### Service Token path scoping — critical
When using service token auth, the token's path scope controls what secrets the operator fetches. A token scoped to `/` ignores the `secretsPath` in the CRD and always returns root secrets. To use sub-path folders (e.g. `/app-name/`), the token **must** be scoped to `/**`.

When creating a service token in the Infisical UI, the "path" field for sub-path access must be `/**` — there is no "grant sub-folder access" checkbox in self-hosted versions, just set the path field literally to `/**`.

### Secret inheritance and the operator
The operator does NOT pass `--include-imports=false`. Root `/` secrets are inherited by all sub-paths by default. This means sub-path managed secrets will also contain root secrets unless you specifically scope the service token to that sub-path only (e.g. `/myapp/**`). For most use cases this is harmless since apps reference specific keys via `secretKeyRef`.

### InfisicalSecret CRD (Universal Auth)
```yaml
apiVersion: secrets.infisical.com/v1alpha1
kind: InfisicalSecret
metadata:
  name: <app>-infisical-sync
  namespace: <namespace>
spec:
  hostAPI: https://<your-infisical-host>
  authentication:
    universalAuth:
      credentialsRef:
        secretName: infisical-auth-token
        secretNamespace: <namespace>
  secretsScope:
    projectSlug: "<project-slug>"
    envSlug: "prod"
    secretsPath: "/<app-name>"
  managedSecretReference:
    secretName: <target-k8s-secret-name>
    secretNamespace: <namespace>
```

### InfisicalSecret CRD (Service Token)
```yaml
apiVersion: secrets.infisical.com/v1alpha1
kind: InfisicalSecret
metadata:
  name: <app>
  namespace: <namespace>
spec:
  hostAPI: http://infisical-infisical-standalone-infisical.infisical.svc.cluster.local:8080/api
  resyncInterval: 60
  authentication:
    serviceToken:
      serviceTokenSecretReference:
        secretName: <namespace>-infisical-token
        secretNamespace: <namespace>
      secretsScope:
        envSlug: dev
        secretsPath: /<app-name>
  managedSecretReference:
    secretName: <target-k8s-secret-name>
    secretNamespace: <namespace>
```

The auth K8s Secret for service tokens:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <namespace>-infisical-token
  namespace: <namespace>
type: Opaque
data:
  infisicalToken: <base64-encoded-service-token>
```

### Folder organization
Group secrets per app: `/<app-name>/` (e.g. `/navidrome/`, `/zipline/`). Avoids key collisions across consumers of one project.

### Auto-reload
Annotate the **Deployment** (not the Secret): `secrets.infisical.com/auto-reload: "true"`. Verify with operator logs showing `AutoRedeployReady: True`.

### Rotating DB passwords (auto-reload race)
Naive ordering (update Infisical → wait for sync → `ALTER USER`) races: the operator updates the K8s Secret and auto-reload restarts the app *before* you run `ALTER`, so the app crashloops against the old DB password.

Safer orderings:
- **Quick:** `ALTER USER ... WITH PASSWORD '<new>'` first, then update Infisical. Existing pooled connections keep working on old creds; the auto-reload restart then comes up cleanly on the new ones.
- **Zero-race:** Remove the auto-reload annotation, change the password in DB and Infisical in any order, `kubectl rollout restart deployment/<app>`, then re-add the annotation.

## Hardening Core Infrastructure (Anti-Inception)

The secret manager and its database **must not** depend on the Infisical Operator — circular dependency, and a self-inflicted recovery nightmare.

- **Postgres root:** Generate a 32+ char password. Store in a manually-created K8s Secret (`postgres-secrets` in `infra`). Reference via `valueFrom.secretKeyRef`. Never plaintext `value:` in the manifest.
- **Infisical core:** Manually-created `infisical-secrets` holds `DB_CONNECTION_URI` (containing the new Postgres password), `AUTH_SECRET`, and `ENCRYPTION_KEY`.

## Security Mandates

- **No plaintext:** any `value: "..."` for a credential is a failure — use `secretKeyRef` or `envFrom`.
- **Entropy:** 32–48 chars for DB passwords, `AUTH_SECRET`, `ENCRYPTION_KEY`.
- **Least privilege:** unique Machine Identity per namespace where possible; at minimum, scope MI to the app's `/path` in Infisical.
- **Cleanup:** delete local `.txt`/`.env` scratch files once secrets land in Infisical.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| `client_id` / `client_secret` (snake_case) in `infisical-auth-token` | Use `clientId` / `clientSecret` — the operator silently fails otherwise |
| Auto-reload annotation on the Secret | It goes on the **Deployment** |
| Update Infisical before `ALTER USER` during DB rotation | Reverse the order, or detach auto-reload |
| `ref:provider:id` string in `openclaw.json` | Use the JSON SecretRef object form |
| Managing Infisical's own DB via the Operator | Anti-inception — use a manual Secret |
| `--raw` on modern CLI | Use `--plain` |
| Service token scoped to `/` used for K8s operator with sub-path folders | Token must be scoped to `/**`; `/`-scoped token always returns root secrets regardless of CRD `secretsPath` |
| Running `infisical secrets set` in a non-existent path | Create the folder first via the REST API — the CLI won't auto-create it |

## Folder Operations

The CLI `infisical secrets folders create` does not accept `--token`. Use the REST API directly:
```bash
curl -s -X POST "$DOMAIN/api/v1/folders" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspaceId":"<id>","environment":"dev","path":"/","name":"<folder-name>"}'
```

Setting secrets in a folder that doesn't exist yet will fail with 404. Create the folder first.

## Operator Placement

The operator can run in the same namespace as Infisical itself (e.g. `infisical`) — it does not need a dedicated `infisical-operator` namespace. Check `kubectl get all -n infisical` before installing; it may already be present.

## Troubleshooting

- **"It looks you have not yet connected this project"** — CLI is looking for a local `.infisical.json`. Pass `--projectId`, `--env`, and a valid `--token`.
- **401 Unauthorized (Universal Auth)** — Machine Identity disabled, credential expired, or wrong `--domain`.
- **InfisicalSecret stuck not syncing** — check operator logs in the operator's namespace; usually MI key casing or wrong `secretsPath`.
- **InfisicalSecret syncing wrong secrets (root secrets instead of sub-path)** — service token is scoped to `/` not `/**`. Create a new token with path `/**`.
- **Token update not taking effect (ETag cache)** — after replacing the auth K8s secret with a new token, the operator caches the old ETag. Annotating the InfisicalSecret is not sufficient. Delete and recreate the InfisicalSecret CRD to force a clean reconcile: `kubectl delete infisicalsecret <name> -n <ns> && kubectl apply -f <file>`.
- **"Folder with path '/foo' not found"** when setting secrets — the folder must be created via the API before secrets can be placed in it (CLI `secrets set` does not auto-create folders).
- **CLI `secrets list` not found** — the subcommand is `infisical secrets` (no `list`). Use `infisical secrets -o dotenv | grep -o '^[^=]*='` to list just keys.
