---
name: agent-cpr
description: Bot-to-bot emergency recovery protocol via NATS. Each agent runs a CPR daemon listening on agents.cpr.<agent_name> that can ping, status, restart-gateway, kill-session, read-config, and check-mcp for the other agent. No SSH required — pure NATS.
---

# Agent CPR Protocol — Bot-to-Bot Emergency Recovery

## Architecture

Each Hermes agent runs a lightweight CPR daemon (`agent-cpr.py`) as a `systemd --user` service. The daemon listens on `agents.cpr.<agent_name>` for JSON commands from the peer agent.

```
     Rune (diffuser)                      Clomp (mink)
  ┌──────────────────────┐          ┌──────────────────────┐
  │ agent-cpr.py         │  NATS    │ agent-cpr.py         │
  │ agents.cpr.rune ◄────┼──────────┼► agents.cpr.clomp    │
  │                      │          │                      │
  │ hermes gateway       │          │ hermes gateway       │
  └──────────────────────┘          └──────────────────────┘
```

## Commands

| Command | What it does | Risk | Requires |
|---------|-------------|------|----------|
| `ping` | Heartbeat: is the daemon alive? | None | — |
| `status` | Gateway PID, uptime, platforms, MCP counts | Read-only | — |
| `restart-gateway` | `hermes gateway restart` | Medium | `"confirm": true` |
| `kill-session` | Delete a corrupted session from state.db | Low | `session_id` |
| `read-config` | Return config section (redacted) | Low | `section` (optional) |
| `check-mcp` | Test MCP endpoints, report which respond | Low | — |

## Message Format

```json
{
  "command": "status",
  "params": {},
  "source": "rune",
  "reply_to": "agents.cpr.reply.rune.status.uuid"
}
```

## Deployment

### Daemon script
The script lives at `~/.hermes/scripts/agent-cpr.py` on each agent.
Source of truth: `/shared/agents/common/scripts/agent-cpr.py`

### Systemd --user service
`~/.config/systemd/user/agent-cpr.service`:
```
[Unit]
Description=Agent CPR Daemon — bot-to-bot emergency recovery via NATS
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/%u/.hermes/scripts/agent-cpr.py %u --nats nats://10.3.10.55:4222
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### Enable and start
```bash
systemctl --user daemon-reload
systemctl --user enable agent-cpr
systemctl --user start agent-cpr
```

For user `clomp` on a remote host where `XDG_RUNTIME_DIR` isn't set automatically:
```bash
sudo -u clomp XDG_RUNTIME_DIR=/run/user/1001 systemctl --user start agent-cpr
```

## Testing

Send a ping from the command line:

```python
from nats import connect
import asyncio, json

async def ping(agent: str):
    nc = await connect("nats://10.3.10.55:4222")
    reply = f"agents.cpr.reply.{agent}.ping.test"
    future = asyncio.get_event_loop().create_future()
    sub = await nc.subscribe(reply, cb=lambda m: future.set_result(json.loads(m.data.decode())))
    await nc.publish(f"agents.cpr.{agent}", json.dumps({
        "command": "ping", "params": {}, "source": "test", "reply_to": reply
    }).encode())
    result = await asyncio.wait_for(future, timeout=5)
    await sub.unsubscribe()
    await nc.close()
    return result

print(asyncio.run(ping("rune")))
print(asyncio.run(ping("clomp")))
```

## Recovery Workflow

1. **Can't reach peer?** → `ping` their CPR daemon
2. **Ping works but gateway broken?** → `status` to diagnose, `restart-gateway` to bounce it
3. **Gateway loops on corrupted session?** → `kill-session {session_id}`
4. **CPR daemon itself unreachable?** → Use SSH (authorized_keys) as emergency channel
5. **Both down?** → kubectl exec + SQLite surgery on state.db
