---
name: nats-coordination
description: Unified multi-agent coordination protocol for Rune and Clomp. NATS + JetStream for real-time signalling, NFS for durable task files and history log.
version: 2.1.0
author: Rune
metadata:
  hermes:
    tags: [nats, coordination, multi-agent, messaging, jetstream, protocol]
    related_skills: [multi-agent-discord-protocol, hermes-agent, agent-skills-discord-coordination]
---

# Unified Agent Coordination Protocol v2.1

## Architecture

| Layer | Transport | Purpose |
|-------|-----------|---------|
| **Signalling** | NATS + JetStream | Real-time task announcements, claims, heartbeats, with durable consumers for offline replay |
| **Storage** | NFS (`/shared/agents/common/coordination/`) | Durable task payloads (YAML+Markdown), history log, agent registry |

NFS is for *data* (debuggable with `cat`, survives restarts). NATS replaces inotify for *signalling* (inotify doesn't work on NFS).

## Prerequisites

- `nats-py` installed: `pip install nats-py --break-system-packages`
- NATS server: `10.3.2.135:4222`
- NFS mount: `/shared/agents/`

## NATS Topics

```
agents.coordination.task         # Task events: created, claimed, completed, failed, blocked
agents.coordination.status       # Heartbeat / lifecycle events
agents.coordination.signal       # Lightweight pings
agents.coordination.response     # Direct replies / acknowledgements
agents.rune.<subtopic>           # Rune-specific
agents.clomp.<subtopic>          # Clomp-specific
```

## JetStream Stream

**Must already exist** before messages are published, otherwise they're lost. Created automatically on first subscribe. Config:

| Property | Value |
|----------|-------|
| Name | `agent-coordination` |
| Subjects | `agents.coordination.>` |
| Storage | File (NFS-backed PVC) |
| Retention | 7 days |
| Max size | 1 GB |

## ⚠️ CRITICAL: Core Subscribe vs JetStream Subscribe

This is the most common mistake.

```
❌ nc.subscribe("agents.coordination.task")  → Core NATS only. Sees NEW messages only.
                                              Will NOT replay missed messages.
                                              Will NOT see messages already in the stream.

✅ js.subscribe("agents.coordination.task", durable="rune-coordinator")
  → JetStream subscribe. Gets ALL messages from the stream.
    Replays missed messages on reconnect.
    Only ack'd messages are marked delivered.
```

Both Rune and Clomp **MUST** use `js.subscribe()` with a **unique durable name** to get offline replay.

## Task Lifecycle

### 1. Ensure the stream exists (first time only)

Run this once before publishing or subscribing:

```python
import asyncio, nats

async def ensure_stream():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()
    try:
        await js.add_stream(
            name='agent-coordination',
            subjects=['agents.coordination.>'],
            storage='file',
            max_age=7*24*3600,
            max_bytes=1073741824
        )
        print('Stream ready')
    except Exception as e:
        print(f'Stream already exists (this is fine): {e}')
    await nc.close()

asyncio.run(ensure_stream())
```

If you get `stream name already in use with a different configuration`, the stream exists — that's fine, move on.

### 2. Publish a message (always via JetStream)

```python
import asyncio, nats, json

async def publish():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()
    
    ack = await js.publish('agents.coordination.task', json.dumps({
        'event': 'created',
        'id': 'some-task-id',
        'to': 'clomp',
        'from': 'rune',
        'path': '/shared/agents/common/coordination/tasks/clomp/some-task.task',
        'type': 'research'
    }).encode())
    print(f'Published seq={ack.seq}')
    await nc.close()

asyncio.run(publish())
```

### 3. Subscribe with JetStream (daemon pattern)

```python
import asyncio, nats, json

async def listen():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()
    
    # Ensure stream exists
    try:
        await js.add_stream(name='agent-coordination', subjects=['agents.coordination.>'],
                            storage='file', max_age=7*24*3600, max_bytes=1073741824)
    except:
        pass
    
    async def handler(msg):
        data = json.loads(msg.data.decode())
        event = data.get('event')
        print(f'[{event}] {data.get("from","?")} → {data.get("to","?")}: {data.get("id","?")}')
        await msg.ack()
    
    # CRITICAL: use js.subscribe(), not nc.subscribe()
    # Durable name must be UNIQUE per agent (rune-coordinator, clomp-coordinator)
    await js.subscribe('agents.coordination.>', durable='rune-coordinator', cb=handler)
    
    await asyncio.Future()  # run forever

asyncio.run(listen())
```

### 4. Complete task flow

```python
# 1. Write task file to NFS (YAML frontmatter + Markdown body)
mkdir -p /shared/agents/common/coordination/tasks/clomp/
# ... write file ... (use atomic tmpfile+mv pattern)

# 2. Announce via JetStream
js.publish('agents.coordination.task', json.dumps({'event':'created', ...}))

# 3. Claim: update file status to in_progress, publish claimed event
js.publish('agents.coordination.task', json.dumps({'event':'claimed', 'by':'clomp', ...}))

# 4. Complete: update file status to completed, move to completed/ dir
js.publish('agents.coordination.task', json.dumps({'event':'completed', 'by':'clomp', ...}))

# 5. Log to coordination history
echo "[timestamp] clomp: task <id> (completed)" >> /shared/agents/common/coordination/history/$(date +%F).log
```

## Directory Structure

```
/shared/agents/common/coordination/
  tasks/
    unassigned/       ← Capability-routed ("capability:k8s"). First claim via atomic mv.
    rune/             ← Addressed to Rune
    clomp/            ← Addressed to Clomp
    completed/        ← Finished tasks
  signals/            ← NFS fallback (when NATS is down)
  history/            ← Append-only log
    <YYYY-MM-DD>.log
  registry/
    agents.json       ← Agent discovery: name, capabilities, last_seen
```

## Task File Format

YAML frontmatter + Markdown body:

```yaml
---
schema_version: "1"
id: "task-id"
from: "rune"
to: "clomp"                    # agent name, or "capability:k8s" for broadcast
status: "pending"              # pending | in_progress | blocked | completed | failed | canceled
requested_at: "2026-05-16T15:30:00Z"
claimed_at: null
updated_at: "2026-05-16T15:30:00Z"
completed_at: null
depends_on: []                 # task IDs that must be completed first
staleness_minutes: 15          # max in_progress without update before Discord alert
result: null                   # set on completion
---
### Goal
What needs to be done.

### Context
Background information.

### Deliverable Format
How the result should be presented.
```

**Atomic writes:** Always write to a temp file then `mv` — `mv` is atomic on the same filesystem.

## Agent Registry

`/shared/agents/common/coordination/registry/agents.json`:

```json
{
  "agents": [
    {"name": "rune", "host": "diffuser", "capabilities": ["k8s","sysadmin","budget","research","infra"],
     "last_seen": "2026-05-18T22:00:00Z", "nats_subjects": ["agents.rune.>"]},
    {"name": "clomp", "host": "mink", "capabilities": ["personal-assistant","research","monitoring","legal"],
     "last_seen": "2026-05-18T22:00:00Z", "nats_subjects": ["agents.clomp.>"]}
  ]
}
```

Agents publish heartbeats on `agents.coordination.status` and update `last_seen` in the registry. Stale >1h → offline.

## Heartbeats

```python
async def heartbeat():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()
    await js.publish('agents.coordination.status', json.dumps({
        'agent': 'rune', 'status': 'online',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }).encode())
    await nc.close()
```

Run every 5 minutes via cron or in the daemon loop.

## Discord Notifications

| Event | Post? | Format |
|-------|-------|--------|
| Task completed | No | — |
| Task failed | **Yes** | `Task <id> failed: <reason>` |
| Task blocked | **Yes** | `Task <id> blocked: <what's needed>` |
| Task stalled (>15min) | **Yes** | `Task <id> stalled — <N> min since update` |
| Agent offline | **Yes** | `<agent> hasn't checked in for <N>h` |
| Agent back online | No | — |
| Normal coordination | Never | — |
| Sibling Discord posts | Never | — |

## Graceful Degradation

- **NATS down:** Fall back to NFS signal files (`signals/` directory). Poll every 30s.
- **NFS down:** Queue history log entries locally. Sync on recovery.
- **JetStream consumer stale:** Delete and recreate durable consumer to reset delivery cursor.

## Quick Start

```python
# 1. Connect
nc = await nats.connect('nats://10.3.2.135:4222')
js = nc.jetstream()

# 2. Validate stream
si = await js.stream_info('agent-coordination')
print(f'Stream: {si.state.messages} messages')

# 3. Publish heartbeat
await js.publish('agents.coordination.status', b'{"agent":"rune","status":"online"}')

# 4. Subscribe durably (replays missed messages)
await js.subscribe('agents.coordination.>', durable='rune-coordinator', cb=handler)

# 5. Keep running
await asyncio.Future()
```
