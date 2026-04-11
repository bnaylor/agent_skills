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

### The Wrapper Script Pattern
To ensure reliable environment propagation and clean output, use a wrapper script (`fetch_secret.sh`) to call the Infisical CLI.

```bash
#!/bin/sh
export INFISICAL_TOKEN=st.xxxx.yyyy.zzzz
export INFISICAL_API_URL=http://your-infisical-instance
# Always use --plain and --silent for clean values
/usr/bin/infisical secrets get "$1" --token="$INFISICAL_TOKEN" --plain --silent --domain $INFISICAL_API_URL --path /
```

## Troubleshooting

- **"It looks you have not yet connected this project"**: Usually means the CLI is trying to find a local `.infisical.json` file. Bypassed by providing `--projectId`, `--env`, and a valid `--token`.
- **401 Unauthorized (Universal Auth)**: Check if the Machine Identity is enabled, if the secret has expired, or if the `--domain` is explicitly provided and correct.
- **Breaking Changes**: 
  - Older CLI versions might use `--raw`.
  - Modern versions use `--plain` for unformatted output.
