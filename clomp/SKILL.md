---
name: clomp
description: Use when administering, configuring, troubleshooting, or SSHing into the local openclaw installation named "clomp" running on host mink.
---

# Clomp — Local OpenClaw Installation Reference

> **Drift policy:** If live discovery reveals values that differ from this skill, either
> restore clomp to the known-good configuration documented here, OR update this skill to
> reflect the new intended state. Never silently leave skill and reality out of sync.

"Clomp" is our on-site openclaw deployment. The name was suggested by Gemini as a portmanteau
of "claw" and the owner's nickname "scromp". It's a genius name.

---

## Host: mink

| Property | Value |
|----------|-------|
| Hostname | `mink` |
| Hardware | Khadas Mind 2 mini-PC |
| CPU | Intel Core Ultra 7 (Meteor Lake) |
| RAM | 64 GB system |
| GPU | NVIDIA RTX 4060 (optional module, 16 GB VRAM) |
| OS | Ubuntu 24.04 (kernel 6.14.0) |
| NPU | Meteor Lake integrated AI accelerator — tracking OpenVINO support, **not ready yet** |

---

## Access & Health

```bash
ssh mink                                      # passwordless SSH as owner
sudo -i                                       # passwordless sudo
sudo su - clomp                               # become the openclaw service user (interactive)
sudo su - clomp -s /bin/bash -c "..."         # run one-off command as clomp
sudo -u clomp /home/clomp/.npm-global/bin/openclaw doctor # overall health check
sudo -u clomp /home/clomp/.npm-global/bin/openclaw ...   # run openclaw CLI directly
```

`openclaw` is in PATH for interactive `clomp` shells (`.bashrc` sets it). For non-interactive
one-liners via `sudo`, use the full path: `/home/clomp/.npm-global/bin/openclaw`.

---

## OpenClaw Version & Files

| Item | Path / Value |
|------|-------------|
| Version | `2026.4.8` (commit `9ece252`) |
| Binary | `/home/clomp/.npm-global/bin/openclaw` |
| Main config | `/home/clomp/.openclaw/openclaw.json` |
| Auth profiles | `/home/clomp/.openclaw/agents/main/agent/auth-profiles.json` |
| Systemd unit | `/home/clomp/.config/systemd/user/openclaw-gateway.service` |
| Log file | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |
| Only agent | `main` |

---

## Operational Commands

All systemd commands require `XDG_RUNTIME_DIR` to be set when running via `sudo` from another user.

```bash
# Status
sudo su - clomp -s /bin/bash -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) systemctl --user status openclaw-gateway"

# Logs (last 50 lines)
sudo su - clomp -s /bin/bash -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) journalctl --user -u openclaw-gateway -n 50"

# Reload config without restart (-f required: process name > 15 chars; must run as clomp)
sudo -u clomp kill -HUP $(pgrep -f openclaw-gateway)

# Reload secrets only (no restart)
sudo -u clomp /home/clomp/.npm-global/bin/openclaw secrets reload

# Restart service
sudo su - clomp -s /bin/bash -c "XDG_RUNTIME_DIR=/run/user/\$(id -u) systemctl --user restart openclaw-gateway"

# Validate config before applying
sudo -u clomp /home/clomp/.npm-global/bin/openclaw doctor --fix
```

---

## Gateway Configuration

| Setting | Value |
|---------|-------|
| Port | `18789` |
| Bind | `lan` (0.0.0.0 — LAN-accessible) |
| Auth mode | Bearer token (value in `openclaw.json` at `gateway.auth.token`) |
| HTTP chatCompletions | **enabled** (`POST /v1/chat/completions`, model must be `"openclaw"`) |
| MCP loopback | `http://127.0.0.1:33885/mcp` (port may vary on restart) |
| Control UI | `allowInsecureAuth: true` ⚠️ (known flag; `openclaw security audit` will warn) |
| Tailscale | off |

---

## Models

### Primary & Heartbeat

| Role | Model |
|------|-------|
| Primary agent | `google/gemini-3.1-flash-lite-preview` |
| Fallback 1 | `ollama/qwen3:14b` (mink local) |
| Fallback 2 | `ollama-diffuser/qwen3:14b` (diffuser local) |
| Fallback 3 | `anthropic/claude-haiku-4-5-20251001` |
| Heartbeat | `ollama/qwen3:14b` (isolatedSession, lightContext) |

### Configured model roster (`agents.defaults.models`)

```
google/gemini-flash-latest
google/gemini-3.1-flash-lite-preview
google/gemini-3.1-pro-preview
anthropic/claude-haiku-4-5-20251001
anthropic/claude-3-5-sonnet-latest
anthropic/claude-sonnet-4-6
anthropic/claude-opus-4-6
ollama/qwen3:14b
ollama/deepseek-r1:14b
ollama-diffuser/qwen3:14b
ollama-diffuser/deepseek-r1:14b
ollama-diffuser/qwen2.5-coder:14b
```

### Local Ollama models (on mink, `localhost:11434`)

```
qwen3:14b            (9.3 GB)   — primary local; current heartbeat model
deepseek-r1:14b      (9.0 GB)
gemma4:26b           (17 GB)
gemma4:e4b           (9.6 GB)
gemma4:e2b           (7.2 GB)
gemma3:27b           (17 GB)
gemma3:4b            (3.3 GB)
gemma2:2b            (1.6 GB)
nomic-embed-text     (274 MB)   — embeddings
tinyllama            (637 MB)   — utility
```

Ollama pull cache: `ollama-cache.naylo.rs:5000` (local registry mirror).

`diffuser` also runs Ollama and is configured as the `ollama-diffuser` provider. Models are
referenced as `ollama-diffuser/<model>` (e.g. `ollama-diffuser/qwen3:14b`).

**Config pattern** (arbitrary provider keys work — not just `ollama`):
```json
"models": {
  "providers": {
    "ollama-diffuser": {
      "baseUrl": "http://diffuser:11434",
      "api": "ollama",
      "apiKey": "ollama",
      "models": [
        {"id": "qwen3:14b", "name": "qwen3:14b"},
        ...
      ]
    }
  }
}
```
⚠️ Both `id` and `name` are required in each model entry — omitting `name` will fail schema
validation and crash the gateway on startup.

Model sets are mostly in sync — known discrepancies as of 2026-04-17:

| Model | mink | diffuser |
|-------|------|----------|
| `gemma2:2b` | ✓ | missing |
| `qwen2.5-coder:14b` | missing | ✓ |
| `qwen3:14b` cache tag | ✓ | missing (pre-cache install) |
| `deepseek-r1:14b` cache tag | missing | missing (both pre-cache) |

Goal is to keep both in sync. When syncing, pull missing models and add cache tags where absent.

### Known model issues

**Small Gemma models (gemma2:2b, gemma3:4b, gemma4:e2b):** Can hold a conversation but
malfunction silently on tool calls. Do not assign these to any role requiring tool use.

**Clomp's self-assessment:** Clomp is deeply convinced that the choice of underlying model
has no bearing whatsoever on its functionality. This is hilarious and incorrect. Model
selection matters — especially for tool-calling reliability.

---

## Auth Profiles (`auth-profiles.json`)

```json
{
  "version": 1,
  "profiles": {
    "google:default":    { "type": "api_key", "provider": "google",    "keyRef": { "source": "exec", "provider": "infisical", "id": "GEMINI_API_KEY" } },
    "anthropic:default": { "type": "api_key", "provider": "anthropic", "keyRef": { "source": "exec", "provider": "infisical", "id": "ANTHROPIC_API_KEY" } },
    "ollama:default":    { "type": "api_key", "provider": "ollama",    "apiKey": "ollama" }
  }
}
```

---

## Secrets (Infisical)

Infisical runs in the on-site k8s cluster. The exec provider script is `/home/clomp/fetch_secret.sh`.

| Setting | Value |
|---------|-------|
| Infisical URL | `http://infisical.mink.local` |
| Service token | Stored in `fetch_secret.sh` (do not echo into logs) |
| Auth method | Infisical service token (`st.*`) scoped to clomp's project |

### Secret IDs referenced in config

| Secret ID | Used for |
|-----------|----------|
| `DISCORD_TOKEN` | Discord bot token |
| `GEMINI_API_KEY` | Google / Gemini auth profile |
| `ANTHROPIC_API_KEY` | Anthropic auth profile |
| `GOOGLE_WEB_SEARCH_API_KEY` | Google web search plugin |

---

## Channels & Plugins

### Discord

| Setting | Value |
|---------|-------|
| Bot name | `@clomp` |
| Bot ID | `1491591851856232601` |
| Guild policy | `allowlist` (all guilds: `"*": {}`) |
| DM policy | `pairing` |
| Status | `online` |
| DM scope | `per-channel-peer` |

### Webhooks

| Route | Path | Session key | Secret |
|-------|------|-------------|--------|
| `siri` | `/plugins/webhooks/siri` | `agent:main:siri` | `clomp_siri_voice` |

Webhook auth: `Authorization: Bearer <secret>` or `X-OpenClaw-Webhook-Secret: <secret>`.

### Other plugins

- `google` — web search via Gemini provider (`tools.web.search.provider: "gemini"`)
- `ollama` — local model access
- `anthropic` — Anthropic model access

---

## Hooks (internal)

| Hook | Config |
|------|--------|
| `session-memory` | summarize_threshold: 40 turns, max_history_turns: 25 |
| `command-logger` | enabled |

---

## Skills

`clawhub:verified` is loaded for all agents by default.

---

## Related Skills

- `openclaw-pro` — generic openclaw configuration, schema rules, safe editing patterns
- `infisical-pro` — Infisical secret management, exec provider protocol
- `microk8s-janitor` — k8s cluster that hosts Infisical

---

## Troubleshooting

1. **Secret Fetch Failures:** Check if `infisical.mink.local` is reachable from `mink`.
2. **Discord Offline:** Check logs for `Rate limit` or `Invalid Token`. Restart service if it hangs on reconnection.
3. **High Latency:** Check `mink` CPU/GPU load (`htop`, `nvidia-smi`). Ollama may be swapping if multiple large models are loaded.
4. **Gateway Unreachable:** Verify `sudo lsof -i :18789`. If bound to `lan` but unreachable, check `ufw` or local network routing.
