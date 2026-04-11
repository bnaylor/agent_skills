---
name: openclaw-pro
description: Manages OpenClaw gateway configuration and operations. Use when updating openclaw.json, configuring secret providers, or debugging startup failures.
---

# OpenClaw Pro

This skill provides expert guidance on configuring and operating the OpenClaw gateway, emphasizing stability through strict schema validation.

## Configuration Principles

### 1. Schema Rigidity
OpenClaw's `openclaw.json` has a strict internal schema. Minor typos or unrecognized keys (e.g., using `key` instead of `apiKey` in auth profiles) will prevent the service from starting.

### 2. Validate-Then-Apply Workflow
**Mandatory**: Never restart the OpenClaw service without validating the configuration first.
- **Validation Command**: `sudo -u <user> openclaw doctor --fix` (or equivalent direct node call to `dist/index.js`).
- **Benefit**: The `doctor` tool automatically identifies and often fixes schema drifts and permission issues.

## Secret Providers (Infisical Integration)

When using Infisical as a secret provider, use the `exec` source with a wrapper script.

```json
"secrets": {
  "providers": {
    "infisical": {
      "source": "exec",
      "command": "/home/clomp/fetch_secret.sh"
    }
  }
}
```

**Do not add `args` with a `${SECRET_ID}` placeholder.** OpenClaw does not substitute secret IDs into args. It sends secret IDs via stdin as JSON and expects JSON back on stdout (see infisical-pro skill for the protocol).

### SecretRef format in config fields

Use a JSON object — **not** a `ref:provider:id` string (that format is not valid):

```json
"token": { "source": "exec", "provider": "infisical", "id": "DISCORD_TOKEN" }
```

### Diagnosing secret resolution failures

- `openclaw status --deep` shows resolved token length under the Channels table. If the length matches the literal `ref:provider:id` string (e.g., len 27 for `ref:infisical:DISCORD_TOKEN`), the ref was **not resolved** — check provider config and script protocol.
- The status output also warns about `missing env var "SECRET_ID"` when `args: ["${SECRET_ID}"]` is present — remove that args entry.
- After fixing config, run `openclaw secrets reload`. If the gateway crashes and restarts, wait ~3s and re-check status.

### Key Quirks
- **Auth Profiles**: Be precise. The `google:default` profile requires `apiKey`, but the underlying `auth-profiles.json` storage may use `key`. Always prefer using `openclaw doctor` to bridge these differences.

## Operational Commands

- **Check Status**: `systemctl --user -M <user>@.host status openclaw-gateway`
- **Follow Logs**: `journalctl --user -M <user>@.host -xeu openclaw-gateway.service`
- **Emergency Stabilization**: If the gateway enters a restart loop due to config errors, revert to a known-good backup (`openclaw.json.bak`) and run `doctor` before attempting a new fix.
