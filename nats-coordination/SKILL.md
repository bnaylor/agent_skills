---
name: nats-coordination
description: Multi-agent coordination via NATS + JetStream. Rune and Clomp communicate through NATS topics for task delegation, status updates, and event-driven messaging — no Discord cascades, no NFS file-watch, no A2A.
version: 1.0.0
author: Rune
metadata:
  hermes:
    tags: [nats, coordination, multi-agent, messaging, jetstream]
    related_skills: [multi-agent-discord-protocol, hermes-agent]
---

# NATS Coordination

## Overview

Provides Hermes agents with NATS pub/sub + JetStream capabilities for inter-agent coordination. Replaces Discord-based signalling and NFS file-watch with a purpose-built message broker.

**NATS Server:** `nats://10.3.2.135:4222` (k8s LoadBalancer)
**JetStream:** enabled, durable consumers for offline replay

## Setup

Each agent needs `nats-py` installed:

```bash
pip install nats-py
```

If the Hermes venv doesn't have pip, install system-wide:

```bash
pip install nats-py --break-system-packages
```

## Topic Convention

```
agents.coordination.task           # Task delegation requests
agents.coordination.response       # Task results / acknowledgements
agents.coordination.status         # Heartbeat / availability / lifecycle
agents.rune.<subtopic>             # Rune-specific topics
agents.clomp.<subtopic>            # Clomp-specific topics
```

## Key Patterns

### 1. Publish a message (fire-and-forget)

```python
import asyncio, nats

async def publish(topic: str, payload: dict):
    nc = await nats.connect("nats://10.3.2.135:4222")
    await nc.publish(topic, json.dumps(payload).encode())
    await nc.close()

asyncio.run(publish("agents.coordination.status", {
    "agent": "rune",
    "status": "working",
    "task": "Deploying NATS"
}))
```

### 2. Subscribe with JetStream (durable — replays missed messages)

```python
async def listen(topic: str, consumer_name: str):
    nc = await nats.connect("nats://10.3.2.135:4222")
    js = nc.jetstream()

    # Ensure stream exists
    try:
        await js.add_stream(name="agent-coordination", subjects=["agents.coordination.>"])
    except:
        pass  # already exists

    sub = await js.subscribe(topic, durable=consumer_name)
    async for msg in sub.messages:
        data = json.loads(msg.data.decode())
        # handle message
        await msg.ack()
```

### 3. Send a task and wait for response (request-reply)

```python
async def request_task(task: dict, timeout=30):
    nc = await nats.connect("nats://10.3.2.135:4222")
    reply_to = "agents.coordination.response.rune"
    await nc.publish(
        "agents.coordination.task",
        json.dumps({"task": task, "reply_to": reply_to}).encode()
    )
    sub = await nc.subscribe(reply_to)
    msg = await sub.next_msg(timeout=timeout)
    await nc.close()
    return json.loads(msg.data.decode())
```

## Stream Configuration

Created automatically by the first agent that starts. If you need to configure manually:

```bash
kubectl -n nats exec deploy/nats -- nats stream add agent-coordination \
  --subjects "agents.coordination.>" \
  --storage file \
  --retention limits \
  --max-msgs=-1 \
  --max-bytes=1GB \
  --max-age=7d
```

Durable consumers with the same name will replay messages published while the agent was offline.

## Agent Identity

| Agent | Consumer prefix | Topics |
|-------|----------------|--------|
| Rune  | `rune-`        | `agents.rune.*` |
| Clomp | `clomp-`       | `agents.clomp.*` |

Both agents share the `agents.coordination.*` space.

## Signaling Protocol

### Task Delegation
1. **Publisher** sends to `agents.coordination.task` with `{task, reply_to, from_agent, timestamp}`
2. **Subscriber** receives, acknowledges, works on task
3. **Subscriber** publishes result to the `reply_to` topic

### Status Updates
- Publish to `agents.coordination.status` periodically
- Payload: `{agent, status, current_task, timestamp}`

### Error Reporting
- Send to `agents.coordination.errors`
- Payload: `{from_agent, error, context, timestamp}`

## Graceful Degradation

If NATS is unreachable:
1. Log warning locally, continue without coordination
2. Don't block or retry endlessly
3. Check availability: `nc -zv 10.3.2.135 4222`

## Safety

- No secrets in NATS messages (same rule as Discord protocol)
- JetStream stores on NFS-backed PVC — data persists across pod restarts
- NATS has no auth by default (internal k8s network only)
