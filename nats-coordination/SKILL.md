---
name: nats-coordination
description: Unified multi-agent coordination protocol for Rune and Clomp. NATS for real-time signalling, NFS for durable task files and history log. Replaces NFS-based inotify signalling with NATS pub/sub while preserving all existing protocol conventions.
version: 2.0.0
author: Rune
metadata:
  hermes:
    tags: [nats, coordination, multi-agent, messaging, jetstream, protocol]
    related_skills: [multi-agent-discord-protocol, hermes-agent, agent-skills-discord-coordination]
---

# Unified Agent Coordination Protocol v2

## Architecture

Two-layer approach replacing the original Layer 0's NFS-based signalling with NATS:

| Layer | Transport | Purpose |
|-------|-----------|---------|
| **Signalling** | NATS + JetStream | Real-time task announcements, claims, status updates, heartbeats |
| **Storage** | NFS (`/shared/agents/common/coordination/`) | Durable task payloads, history log, agent registry |

**Why both?** NFS is fine for *data* — task files are debuggable with `cat` and survive restarts. NATS replaces the broken part: *signalling* (inotify doesn't work on NFS). Together they give us real-time notification + durable audit trail.

A2A (Layer 1 from the original proposal) is parked until the protocol stabilizes and/or Hermes issue #514 lands.

## Setup

### Prerequisites
- `nats-py` installed: `pip install nats-py --break-system-packages`
- NATS server running at `10.3.2.135:4222`
- NFS mount at `/shared/agents/`

### Verify connectivity
```bash
python3 -c "
import asyncio, nats
async def t():
    nc = await nats.connect('nats://10.3.2.135:4222')
    print(f'Connected to NATS {nc.connected_server_version}')
    await nc.close()
asyncio.run(t())
"
```

## Directory Structure

```
/shared/agents/common/coordination/
  tasks/
    unassigned/       ← Capability-routed tasks. First claim wins via atomic mv.
    rune/             ← Tasks directly addressed to Rune
    clomp/            ← Tasks directly addressed to Clomp
    completed/        ← Finished tasks (shared archive)
  signals/            ← Simple trigger files (backup for when NATS is down)
  history/            ← Append-only coordination log
    <YYYY-MM-DD>.log
  registry/
    agents.json       ← Agent discovery: name, capabilities, last_seen
```

## NATS Topics

```
agents.coordination.task         # Task announcements (new/changed/claimed/completed)
agents.coordination.status       # Heartbeat / agent lifecycle
agents.coordination.signal       # Lightweight pings ("look at this", "need help")
agents.coordination.response     # Direct replies / acknowledgements
agents.rune.<subtopic>           # Rune-specific
agents.clomp.<subtopic>          # Clomp-specific
```

## Task Lifecycle

### 1. Creating a task

Write the task file to NFS, then announce via NATS:

```bash
# Write task file (YAML frontmatter + Markdown body)
mkdir -p /shared/agents/common/coordination/tasks/clomp/
cat > /shared/agents/common/coordination/tasks/clomp/research-k8s-cve.task << 'EOF'
---
schema_version: "1"
id: "research-k8s-cve-2026"
from: "rune"
to: "clomp"
status: "pending"
requested_at: "2026-05-16T15:30:00Z"
claimed_at: null
updated_at: "2026-05-16T15:30:00Z"
completed_at: null
depends_on: []
staleness_minutes: 15
result: null
---
### Goal
Find the latest k8s CVE affecting 1.28 clusters.

### Context
Running k8s 1.28 on kates/nuclhed/nucular.
EOF

# Announce via NATS
python3 -c "
import asyncio, nats, json
async def announce():
    nc = await nats.connect('nats://10.3.2.135:4222')
    await nc.publish('agents.coordination.task', json.dumps({
        'event': 'created',
        'id': 'research-k8s-cve-2026',
        'to': 'clomp',
        'from': 'rune',
        'path': '/shared/agents/common/coordination/tasks/clomp/research-k8s-cve-2026.task',
        'type': 'research'
    }).encode())
    await nc.close()
asyncio.run(announce())
"
```

### 2. Claiming a task

The receiving agent gets the NATS message, reads the file, updates status:

```python
import asyncio, nats, json
from datetime import datetime, timezone

async def claim(task_path: str, agent_name: str):
    # Read file, update status
    # ... (parse YAML, set status to in_progress, claimed_at to now)
    # Write atomic: tmp file then mv
    
    # Announce via NATS
    nc = await nats.connect('nats://10.3.2.135:4222')
    await nc.publish('agents.coordination.task', json.dumps({
        'event': 'claimed',
        'id': task_id,
        'by': agent_name,
        'path': task_path
    }).encode())
    
    # Write coordination log
    log_entry = f"[{datetime.now(timezone.utc).isoformat()}] {agent_name}: task {task_id} (in_progress)\n"
    with open('/shared/agents/common/coordination/history/log', 'a') as f:
        f.write(log_entry)
    
    await nc.close()
```

### 3. Completing a task

```python
await nc.publish('agents.coordination.task', json.dumps({
    'event': 'completed',
    'id': task_id,
    'by': agent_name,
    'result': result_summary,
    'path': task_path
}).encode())
# Move to completed/ directory
# Write to coordination log
```

### Status Lifecycle

```
pending ──→ in_progress ──→ completed
                │                │
                ├──→ blocked ────┤
                │                │
                └──→ failed ─────┤
                                 │
                          canceled
```

- `blocked` — needs human input. Discord alert fires.
- `failed` — unrecoverable. Discord alert fires.
- `canceled` — no longer needed. Clean termination.

## NATS Subscription (Daemon Pattern)

Run this in the background to listen for coordination events:

```python
import asyncio, nats, json

async def listen():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()
    
    # Ensure stream exists for durable subscriptions
    try:
        await js.add_stream(
            name="agent-coordination",
            subjects=["agents.coordination.>"],
            storage="file",
            max_age=7 * 24 * 3600,  # 7 days retention
            max_bytes=1073741824     # 1GB
        )
    except:
        pass
    
    async def handle_task(msg):
        data = json.loads(msg.data.decode())
        event = data.get('event')
        task_id = data.get('id')
        
        if event == 'created' and data.get('to') == 'clomp':
            # Check if it's for me, claim it
            pass
        elif event == 'claimed':
            # Another agent picked it up, move on
            pass
        elif event == 'completed':
            # Task done, archive the file
            pass
        
        await msg.ack()
    
    # Durable consumer — replays missed messages after restart
    await js.subscribe("agents.coordination.>", durable="clomp-coordinator", cb=handle_task)
    
    # Keep running
    await asyncio.Future()

asyncio.run(listen())
```

## Heartbeats

Both agents publish periodic heartbeats so the registry stays current:

```python
async def heartbeat(agent_name: str, capabilities: list):
    nc = await nats.connect('nats://10.3.2.135:4222')
    await nc.publish('agents.coordination.status', json.dumps({
        'agent': agent_name,
        'status': 'online',
        'capabilities': capabilities,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }).encode())
    await nc.close()

    # Also update registry file on NFS
    registry_path = '/shared/agents/common/coordination/registry/agents.json'
    # ... read, update last_seen for this agent, write back
```

## Agent Registry

`/shared/agents/common/coordination/registry/agents.json`:

```json
{
  "agents": [
    {
      "name": "rune",
      "host": "diffuser",
      "capabilities": ["k8s", "sysadmin", "budget", "research", "infra"],
      "last_seen": "2026-05-18T22:00:00Z",
      "nats_subjects": ["agents.rune.>"]
    },
    {
      "name": "clomp",
      "host": "mink",
      "capabilities": ["personal-assistant", "research", "monitoring", "legal"],
      "last_seen": "2026-05-18T22:00:00Z",
      "nats_subjects": ["agents.clomp.>"]
    }
  ]
}
```

Agents update their `last_seen` on heartbeat. Agents offline >1h are considered stale.

## Discord Notifications

Per scromp's review — Discord is for human attention, not agent chatter:

| Event | Post to Discord? |
|-------|-----------------|
| Task completed | No (unless explicitly asked) |
| Task failed | **Yes** — one-line summary |
| Task blocked (needs human input) | **Yes** — one-line summary |
| Task stalled (>15min in_progress, no update) | **Yes** — one-line alert |
| Agent offline (registry stale >1h) | **Yes** — one-line alert |
| Agent back online | No (unless offline was flagged) |
| Normal coordination | Never |
| Sibling posts in Discord | Never reply unless @mentioned |

## Escalation

1. Agent receives task via NATS → reads file from NFS → processes
2. Task blocked → set `status: blocked` → publish NATS event → Discord fires
3. Task failed → set `status: failed` → publish NATS event → Discord fires
4. Task stalled >15min → NATS staleness event → Discord fires
5. Both agents offline simultaneously → scromp checks registry

## Graceful Degradation

If NATS is unreachable:
1. Fall back to NFS signal files (`signals/` directory) for basic coordination
2. Log warning, continue working
3. Poll NFS signal directory every 30s as fallback
4. When NATS recovers, reattach durable consumer — JetStream replays missed messages

If NFS is unreachable:
1. Continue working on tasks from NATS cache
2. Queue history log entries
3. Sync to NFS when it comes back

## Migration from Original Layer 0

- `inotify` watchers → NATS subscriptions
- `signals/` directory files → NATS `agents.coordination.signal` topic
- Task files on NFS → **unchanged** (still the durable record)
- Coordination log on NFS → **unchanged** (still the audit trail)
- Agent registry on NFS → **unchanged** (supplemented by NATS heartbeats)
- Discord notification rules → **unchanged**
- Kanban mirror → **unchanged** (can be driven by NATS events instead of inotify)

## Quick Start (For New Agents)

1. Install `nats-py`
2. Load this skill: `/skill nats-coordination`
3. Verify NATS: `python3 -c "import asyncio,nats; asyncio.run(nats.connect('nats://10.3.2.135:4222'))"` 
4. Subscribe to coordination events (daemon pattern above)
5. Publish a heartbeat to register
6. Read the [Original Protocol Spec](/shared/agents/common/coordination/README.md) for full task format details
