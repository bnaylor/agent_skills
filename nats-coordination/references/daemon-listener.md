# NATS Coordination Daemon Listener

The polling-based listener at `/shared/agents/common/scripts/nats-listener.py` is the canonical daemon for both agents.

## Architecture

Instead of push-based JetStream subscribe (which silently delivers zero messages in nats-py v2.14), the daemon uses a simple polling loop:

```
Every 10s:
  1. Get stream_info() → check last_seq
  2. If last_seq > state.last_seq:
     For each new seq:
       js.get_msg() → decode → log event
     Update state.last_seq
  3. Save state to ~/.hermes/.nats-listener-state.json
  4. Sleep 10s
```

## State Tracking

- **State file:** `~/.hermes/.nats-listener-state.json` — stores `last_seq` so reboots don't replay old messages
- **Log file:** `~/.hermes/logs/nats-listener.log` — chronological event log for debugging
- **Coordination history:** `/shared/agents/common/coordination/history/<date>.log` — shared NFS audit trail

## Per-Agent Configuration

Each agent instance needs a unique identity. The script uses a `CONSUMER` variable (currently `rune-coordinator`). For Clomp, change it to `clomp-coordinator`.

## Running as a Daemon

### Background process (simple)
```bash
python3 /shared/agents/common/scripts/nats-listener.py &
```

### Hermes background task
Within a Hermes session, start via terminal:
```
terminal(command="python3 /shared/agents/common/scripts/nats-listener.py", background=true)
```

### systemd (for persistent operation)
```ini
[Unit]
Description=NATS Coordination Listener
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /shared/agents/common/scripts/nats-listener.py
Restart=always
RestartSec=5
User=agent

[Install]
WantedBy=multi-user.target
```
