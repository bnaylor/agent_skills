---
name: openclaw-pro
description: Use when updating openclaw.json, configuring secret providers, debugging startup or subagent auth failures, setting up webhooks, enabling the HTTP chat endpoint, or editing gateway config safely.
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
- **`doctor` does NOT support `--config <path>`** — it always validates the live `openclaw.json`. The safe pre-apply workflow is: backup → apply staged file → run doctor → revert from backup if doctor fails.

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

### Auth Profiles (`auth-profiles.json`)

This file is **separate from `openclaw.json`** and lives at `~/.openclaw/agents/<agentId>/agent/auth-profiles.json`. Missing entries here silently break subagents while the main agent works fine — the main agent may have keys cached, but subagents do a fresh lookup.

Each provider entry uses `keyRef` for Infisical-backed resolution:

```json
{
  "version": 1,
  "profiles": {
    "google:default": {
      "type": "api_key",
      "provider": "google",
      "keyRef": { "source": "exec", "provider": "infisical", "id": "GEMINI_API_KEY" }
    },
    "anthropic:default": {
      "type": "api_key",
      "provider": "anthropic",
      "keyRef": { "source": "exec", "provider": "infisical", "id": "ANTHROPIC_API_KEY" }
    }
  }
}
```

If subagents fail with `"No API key found for provider X"` but the main agent works, the entry for that provider is missing from this file.

### Key Quirks
- **Web search provider naming**: The Google plugin registers its web search provider as `"gemini"`, not `"google"`. Setting `tools.web.search.provider: "google"` triggers a `WEB_SEARCH_PROVIDER_INVALID_AUTODETECT` warning and falls back to auto-detect. Use `"gemini"` explicitly.
- `openclaw secrets reload` clears warnings about unresolved secrets without a gateway restart.

## Webhooks Plugin

The webhooks plugin is a **TaskFlow orchestration API** — not a simple message relay. A common mistake is sending `{"action":"message","text":"..."}` which returns `"action: Invalid input"`.

**Auth**: The route `secret` field acts as a per-route Bearer token, bypassing the global gateway token. Use `Authorization: Bearer <secret>` or `X-OpenClaw-Webhook-Secret: <secret>`.

**Valid actions**: `create_flow`, `get_flow`, `list_flows`, `find_latest_flow`, `resolve_flow`, `get_task_summary`, `set_waiting`, `resume_flow`, `finish_flow`, `fail_flow`, `request_cancel`, `cancel_flow`, `run_task`.

```bash
# Minimal fire-and-forget example
curl -X POST http://<host>/plugins/webhooks/<route> \
  -H "Authorization: Bearer <secret>" \
  -H "Content-Type: application/json" \
  -d '{"action":"create_flow","goal":"do something"}'
```

Flows start in `"queued"` status. They only execute if an agent is actively watching the bound `sessionKey`. Without that, flows accumulate but nothing runs.

## OpenAI-Compatible HTTP Endpoint

Disabled by default. Enable with:

```json
"gateway": {
  "http": {
    "endpoints": {
      "chatCompletions": { "enabled": true }
    }
  }
}
```

- **URL**: `POST /v1/chat/completions`
- **Auth**: main gateway Bearer token
- **Model**: must be `"openclaw"` (not a provider model string like `"google/gemini-flash-latest"`)
- **Session routing** (in priority order):
  1. `X-OpenClaw-Session-Key` header → exact key used
  2. `"user"` field in body → stable key `agent:<id>:openai-user:<user>` (persistent across requests)
  3. Neither → new random UUID session per request

```bash
curl -X POST http://<host>/v1/chat/completions \
  -H "Authorization: Bearer <gateway-token>" \
  -H "Content-Type: application/json" \
  -d '{"model":"openclaw","messages":[{"role":"user","content":"hello"}],"user":"siri"}'
```

## Operational Commands

- **Check Status**: `systemctl --user -M <user>@.host status openclaw-gateway`
- **Follow Logs**: `journalctl --user -M <user>@.host -xeu openclaw-gateway.service`
- **Reload config** (no restart): `kill -HUP $(pgrep -f openclaw-gateway)` — note `-f` is required since the process name exceeds 15 characters
- **Reload secrets only**: `openclaw secrets reload` — no restart needed for auth/secret changes
- **Restart from outside** (e.g. via ssh as root): `sudo su - <user> -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) systemctl --user restart openclaw-gateway"`
- **Emergency Stabilization**: If the gateway enters a restart loop due to config errors, revert to a known-good backup (`openclaw.json.bak`) and run `doctor` before attempting a new fix.

## Environment Variables for the Gateway and Subagents

`.bashrc` and `.profile` are **not** sourced by systemd user services. Environment variables needed by the gateway or tools it spawns must be set via `~/.config/environment.d/`:

```bash
# Create (chmod 600 — may contain secrets)
echo "MY_VAR=value" > ~/.config/environment.d/myvar.conf
chmod 600 ~/.config/environment.d/myvar.conf

# Apply without a full session restart
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user daemon-reload
XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user restart openclaw-gateway
```

Verify the var landed in the gateway process: `sudo cat /proc/$(pgrep -f openclaw-gateway | head -1)/environ | tr "\0" "\n" | grep MY_VAR`

Subagents inherit the gateway's environment, so this propagates automatically — no prompt changes needed.

## Config Editing Safety

**Never** pipe read → transform → write in a single shell pipeline:

```bash
# DANGEROUS — write starts before parse completes, silently clobbles file on transform failure
ssh host 'cat config.json' | python3 -c "..." | ssh host 'cat > config.json'
```

Safe pattern: fetch locally → transform locally → stage on remote → backup → apply → validate → revert if needed:

```bash
# Fetch and edit locally
ssh host 'sudo -u clomp cat ~/.openclaw/openclaw.json' > /tmp/openclaw.json
# ... edit /tmp/openclaw.json ...

# Stage on remote (use a writable path, e.g. the SSH user's home dir)
cat /tmp/openclaw.json | ssh host 'cat > ~/openclaw_stage.json'
ssh host 'sudo cp ~/openclaw_stage.json /home/clomp/.openclaw/openclaw.json && \
          sudo chown clomp:clomp /home/clomp/.openclaw/openclaw.json'

# Validate (doctor always reads the live file — no --config flag)
ssh host 'sudo -u clomp openclaw doctor'
# If doctor fails: ssh host 'sudo -u clomp cp ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json'

# Reload (no restart needed for config changes)
ssh host 'sudo -u clomp kill -HUP $(pgrep -f openclaw-gateway)'
```

Note: `pgrep -f openclaw-gateway` inside a subshell may match itself; if HUP fails, get the PID first with a separate `pgrep` call and pass it directly.
