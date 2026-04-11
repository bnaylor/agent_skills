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

When using Infisical as a secret provider, use the `exec` source combined with a wrapper script.

```json
"secrets": {
  "providers": {
    "infisical": {
      "source": "exec",
      "command": "/home/clomp/fetch_secret.sh",
      "args": ["\${SECRET_ID}"]
    }
  }
}
```

### Key Quirks
- **Variable Syntax**: Use `\${SECRET_ID}` (escaped in the JSON write) to ensure OpenClaw passes the correct secret key to the command.
- **Auth Profiles**: Be precise. The `google:default` profile requires `apiKey`, but the underlying `auth-profiles.json` storage may use `key`. Always prefer using `openclaw doctor` to bridge these differences.

## Operational Commands

- **Check Status**: `systemctl --user -M <user>@.host status openclaw-gateway`
- **Follow Logs**: `journalctl --user -M <user>@.host -xeu openclaw-gateway.service`
- **Emergency Stabilization**: If the gateway enters a restart loop due to config errors, revert to a known-good backup (`openclaw.json.bak`) and run `doctor` before attempting a new fix.
