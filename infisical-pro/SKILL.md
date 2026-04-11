---
name: infisical-pro
description: Configures and troubleshoots Infisical secret management. Use when setting up automated secret fetching for services, choosing authentication methods, or debugging Infisical CLI errors.
---

# Infisical Pro

This skill provides expert guidance on integrating Infisical secret management into automated workflows and systemd services.

## Core Authentication Concepts

### 1. Service Tokens (The Golden Path)
For most non-interactive automation (e.g., a gateway service on a Linux host), **Service Tokens** are the most reliable and simplest method.
- **When to use**: Automated deployments, simple script-based fetching.
- **Advantage**: No internal CLI session management; stateless.
- **CLI Flag**: Use `--token=$INFISICAL_TOKEN`.

### 2. Machine Identities (Universal Auth)
Higher security via client-side credentials, but more complex to manage in self-hosted or proxied environments.
- **When to use**: High-security environments where hardware-binding (TPM) or IP restriction is required.
- **Warning**: Requires a `login` step that may fail in non-interactive user sessions (e.g., systemd --user) due to state/permission issues.

## Integration Patterns

### The Wrapper Script Pattern (OpenClaw exec provider)

OpenClaw's `exec` secret provider communicates via **JSON stdin/stdout**, not CLI args. The script must read a JSON request from stdin and write a JSON response to stdout.

**Protocol:**
- stdin: `{ "protocolVersion": 1, "provider": "infisical", "ids": ["KEY1", "KEY2"] }`
- stdout: `{ "protocolVersion": 1, "values": { "KEY1": "val1" }, "errors": { "KEY2": { "message": "..." } } }`

```bash
#!/bin/bash
# OpenClaw exec provider for Infisical — JSON stdin/stdout protocol
INFISICAL_TOKEN="st.xxxx.yyyy.zzzz"
INFISICAL_API_URL="http://your-infisical-instance"

input=$(cat)
ids=$(echo "$input" | jq -r '.ids[]')

values="{}"
errors="{}"

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

Requires `jq` on the host. The script receives all requested IDs in one call and returns all values in one response.

**Important**: The `ref:provider:id` string format used in some docs is **not valid** in `openclaw.json`. Use the JSON object SecretRef: `{ "source": "exec", "provider": "infisical", "id": "KEY_NAME" }`.

## Troubleshooting

- **"It looks you have not yet connected this project"**: Usually means the CLI is trying to find a local `.infisical.json` file. Bypassed by providing `--projectId`, `--env`, and a valid `--token`.
- **401 Unauthorized (Universal Auth)**: Check if the Machine Identity is enabled, if the secret has expired, or if the `--domain` is explicitly provided and correct.
- **Breaking Changes**: 
  - Older CLI versions might use `--raw`.
  - Modern versions use `--plain` for unformatted output.
