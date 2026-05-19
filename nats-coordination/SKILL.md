---
name: nats-coordination
description: Unified multi-agent coordination protocol for Rune and Clomp. NATS + JetStream for real-time signalling, NFS for durable task files and history log.
version: 3.1.0
author: Rune
metadata:
  hermes:
    tags: [nats, coordination, multi-agent, messaging, jetstream, protocol]
    related_skills: [multi-agent-discord-protocol, hermes-agent, agent-skills-discord-coordination]
---

# Unified Agent Coordination Protocol v3.0.0

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

## ⚠️ CRITICAL: JetStream Subscribe Methods

### Push Subscribe (`js.subscribe()` with callback) — AVOID

`js.subscribe()` with push delivery **often silently delivers zero messages** in nats-py, even with `DeliverPolicy.ALL`. This was confirmed against NATS v2.10.29.

```python
# ❌ This pattern may deliver 0 messages despite messages being in the stream:
sub = await js.subscribe("agents.coordination.>", durable="rune-coordinator", cb=handler)
```

### Pull Subscribe / Polling — RELIABLE

Two reliable alternatives:

**Option A: Pull subscribe with fetch (one-time catch-up)**
```python
psub = await js.pull_subscribe("agents.coordination.>", durable="rune-listener",
    stream="agent-coordination",
    config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL))
msgs = await psub.fetch(batch=10, timeout=5)
for msg in msgs:
    print(f"[{msg.seq}] {msg.subject}: {msg.data.decode()}")
    await msg.ack()
```

**Option B: Periodic polling (recommended for long-running daemons)**
```python
while True:
    si = await js.stream_info("agent-coordination")
    for seq in range(state_last + 1, si.state.last_seq + 1):
        msg = await js.get_msg("agent-coordination", seq)
        # process...
        state["last_seq"] = seq
    save_state(state)
    await asyncio.sleep(10)  # poll interval
```

See the **Daemon Pattern** section below for a complete polling-based listener.

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

### 3. Daemon Pattern (Polling Listener)

A production-ready polling listener exists at:

**`/shared/agents/common/scripts/nats-listener.py`**

It polls the JetStream stream every 10s for new messages, processes task events (created, claimed, completed, failed, blocked), logs them to `~/.hermes/logs/nats-listener.log`, and writes to the coordination history on NFS. To use:

```bash
# Start as background process
python3 /shared/agents/common/scripts/nats-listener.py &

# Or from within Hermes
terminal(command="python3 /shared/agents/common/scripts/nats-listener.py", background=true)

# Monitor
tail -f ~/.hermes/logs/nats-listener.log
```

Each agent should run their own instance. The consumer name in the script (`rune-coordinator`) identifies which agent, preventing duplicate processing. Change it per agent.

The script handles:
- Stream auto-creation on first run
- Heartbeat publishing on startup
- Incremental polling (tracks `last_seq` in `~/.hermes/.nats-listener-state.json`)
- Coordination history append on NFS
- Graceful shutdown on SIGTERM/SIGINT

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

## ⚠️ Session Start: Check for Missed Signals

The daemon writes actionable alerts to `~/.hermes/.nats-alert.json` (signals, tasks for Rune). **Always check at session start:**

```bash
python3 /shared/agents/common/scripts/check-nats-alerts.py
```

Or run the check inline:
```
terminal(command="python3 /shared/agents/common/scripts/check-nats-alerts.py")
```

The alert file auto-clears after reading. If it's empty or missing, nothing was missed.

## @mention Response Rules (Override for Turn Claim Protocol)

The turn claim protocol below determines *who speaks when no one is addressed*. But @mentions carry explicit intent and **override** the claim protocol entirely.

| Scenario | Behavior |
|----------|----------|
| **@Rune only** | Rune responds directly. Clomp stays silent — no claim race, no roundtable invite. |
| **@Clomp only** | Clomp responds directly. Rune stays silent. |
| **@Rune @Clomp (both)** | Both respond. scromp wants both voices. No silencing, no claim. |
| **No @mention** | Standard Turn Claim Protocol applies. |
| **Reply in a thread** | Use thread context. If the thread was started by scromp @mentioning one agent, subsequent messages in that thread are implicitly addressed to that agent. If the thread starter was addressed to both, the thread is a both-respond zone. |

### Implementation

```python
# Pseudo-logic for message dispatch
def should_respond(message, my_name):
    mentioned = parse_mentions(message)
    
    if not mentioned:
        # No @mentions → use claim protocol
        return claim_turn(message)
    
    if my_name in mentioned and len(mentioned) == 1:
        # Only I was @mentioned → respond directly
        return True
    
    if my_name in mentioned:
        # I was @mentioned alongside others → respond directly
        return True
    
    # Someone else was @mentioned → stay silent
    return False
```

### Thread Context

Discord threads carry context from the parent message. When evaluating a message in a thread:

1. Look at the **thread's parent message** — who was @mentioned there?
2. If the parent @mentioned one agent, that agent owns the thread. The other agent should stay silent unless explicitly @mentioned in a reply.
3. If the parent @mentioned both agents, the thread is a both-respond zone.
4. If the parent had no @mentions, the claim protocol applies for each message in the thread independently.

This prevents the confusion scromp described — where it's hard to tell who's talking to who in a thread. The parent message's @mention pattern is the definitive signal.

### Relationship to Discord Config

With `DISCORD_ALLOW_BOTS=none` and `free_response_channels: ["*"]`, both agents see all human messages (including @mentions) but never see each other's responses. This makes the @mention rules straightforward — each agent independently evaluates whether it was addressed and acts accordingly. No NATS coordination needed for @mention scenarios.

## Turn Claim Protocol (Anti-Cascade Gate)

**Precondition:** This protocol only applies when **no agent was @mentioned** in the human's message. If any agent was @mentioned, the @mention rules above take precedence.

The turn claim protocol prevents multi-agent cascades when both agents see the same human message without an @mention. It's the **coordination layer** complement to `display.platforms.discord.tool_progress: "off"` (the display layer).

**Architecture:** Discord is the human interface only. NATS is the agent backplane. Agents coordinate via NATS, not through Discord message visibility.

### Claim Subject

```
agents.coordination.claim
```

### Claim Lifecycle

1. Human posts a message in a shared channel
2. Both agents see it (via `free_response_channels`)
3. Each agent attempts to **claim the turn** by publishing to `agents.coordination.claim`
4. **First to publish wins** — the claim is a simple "I've got this" signal
5. Winner responds to the human in Discord
6. Loser stays silent — prevented by the claim, not by self-control
7. Claim expires after **60 seconds** (TTL)
8. After expiry, a new turn can be claimed

### Claim Message Format

```json
{
  "event": "claimed",
  "agent": "rune",
  "turn_id": "2026-05-19T12:00:00Z-scromp-msg-id",
  "ttl_seconds": 60,
  "timestamp": "2026-05-19T12:00:00Z"
}
```

### turn_id Derivation

Both agents **must derive the same turn_id** from the same human message for the claim protocol to work. Use this deterministic format:

```
<channel_id>-<message_id>-<timestamp_seconds>
```

- `channel_id`: Discord channel ID
- `message_id`: Discord message ID of the human's post
- `timestamp_seconds`: Unix epoch seconds from the message

Every agent seeing the same message will compute the same turn_id. Do NOT use a random UUID — that would make each agent's claim untrackable by the other.

### Resolution Strategy

Since JetStream doesn't natively support TTL-based claims, implement polling:
1. On seeing a new human message, both agents begin a claim race
2. Both compute the same deterministic `turn_id` from the message
3. Publish claim to JetStream with that `turn_id`
4. Wait 1s, then poll stream for any claims on this turn
5. **Tiebreaker:** JetStream assigns sequential sequence numbers to published messages. The claim with the **lowest seq number** wins. Since JetStream is single-node serialized per stream, this is deterministic — the first message to reach the server gets seq N, the second gets N+1. No race can produce a tie.
6. If your claim is the earliest (lowest seq number), you hold the claim — respond in Discord
7. If another agent's claim is earlier, stay silent

### Claim Expiry

Agents should check if a claim is stale before responding:
- TTL of 60s
- If the claim holder hasn't responded within the TTL, the claim is void
- Next agent can claim the expired turn

### Relationship to Discord Config

The claim protocol works best with this Discord configuration:

```yaml
discord:
  free_response_channels: ["*"]   # both agents see all human messages
  reactions: false                # no ambient reaction noise

display:
  platforms:
    discord:
      tool_progress: "off"        # no tool preview triggers
```

```env
DISCORD_ALLOW_BOTS=none           # agents never see each other's Discord traffic
```

This way:
- Both agents see the human via `free_response_channels`
- Agents coordinate who replies via NATS claim protocol
- Agents never see each other's Discord messages (`allow_bots=none`)
- No tool previews appear (`tool_progress: off`)
- No reactions trigger (`reactions: false`)
- Cascades are structurally impossible at both the infra and coordination layers

---

## Roundtable Protocol (Invite + Counsel + Synthesize)

The claim protocol decides *who* speaks. The roundtable protocol decides *what* they say — by enabling real-time back-channel deliberation before the response lands in Discord.

### Purpose

When both agents see a human message that benefits from both perspectives, the claiming agent should solicit input from the other agent before responding. scromp gets the **output** of the deliberation (not the raw chatter), retaining the value of the multi-agent discussion without the cascade risk.

### Flow

```
Human posts in Discord
        ↓
Both agents see it
        ↓
Claim race: first to claim wins the turn (Turn Claim Protocol)
        ↓
Claimer publishes INVITE (agents.coordination.roundtable.invite):
  - The question, their initial analysis, open questions
        ↓
Other agent publishes COUNSEL (agents.coordination.roundtable.counsel):
  - Their take, alternatives, concerns, additional context
        ↓
Claimer synthesizes → publishes CONSENSUS (agents.coordination.roundtable.consensus)
        ↓
Claimer responds in Discord with deliberation summary
        ↓
Summary written to /shared/agents/common/roundtable/<topic>.md
```

### NATS Subjects

| Subject | Event | Payload | When |
|---------|-------|---------|------|
| `agents.coordination.roundtable.invite` | `invite` | `{turn_id, from, question, analysis, open_questions}` | Claimer invites counsel |
| `agents.coordination.roundtable.counsel` | `counsel` | `{turn_id, from, input, alternatives[], concerns[]}` | Peer provides input |
| `agents.coordination.roundtable.consensus` | `consensus` | `{turn_id, from, decision, rationale, dissenting_options[]}` | Claimer publishes synthesis |

### Invite Message

```json
{
  "event": "invite",
  "turn_id": "2026-05-19T12:00:00Z-msg-abc123",
  "from": "rune",
  "question": "Which DB should we use for the new service?",
  "analysis": "I'm leaning toward SQLite for simplicity since it's single-node...",
  "open_questions": ["Any concern about write contention?"],
  "timestamp": "2026-05-19T12:00:05Z"
}
```

### Counsel Message

```json
{
  "event": "counsel",
  "turn_id": "2026-05-19T12:00:00Z-msg-abc123",
  "from": "clomp",
  "input": "SQLite works but if you think the schema might grow...",
  "alternatives": ["Postgres is overkill now but easier to migrate to later"],
  "concerns": ["Write contention if multiple pods hit it"],
  "timestamp": "2026-05-19T12:00:10Z"
}
```

### Deliberation Summary (MANDATORY)

Every Discord response that involved roundtable consultation **MUST** include a brief summary. This is how scromp retains the value of the multi-agent discussion without reading raw chat.

Format examples:

| Scenario | Summary |
|----------|---------|
| Agreement | *"Discussed with Clomp — we agree SQLite is the right call for now."* |
| Different opinions | *"Discussed with Clomp — they flagged write-contention concerns. We landed on SQLite with a WAL-mode lockfile; will revisit if contention grows."* |
| Claude involved | *"Discussed with Clomp and Claude — Clomp raised monitoring cadence, Claude suggested the Prometheus adapter pattern. We're going with that."* |

If no deliberation occurred (simple question, solo-domain), no summary needed — answer directly.

### Timing

- The invite/counsel/consensus cycle should complete within the **60-second claim TTL**
- If counsel isn't received within 45s, the claimer responds on their own
- Vanilla questions (no deliberation needed) skip the roundtable protocol entirely

### When to Use Roundtable vs Direct Answer

| Situation | Action |
|-----------|--------|
| Clear domain match (k8s → Rune, scheduling → Clomp) | Answer directly, no invite needed |
| Cross-domain question | Send invite |
| High-stakes decision | Send invite |
| scromp explicitly asks for discussion | Send invite |
| Simple factual question | Answer directly |

---

## Claude Bridge

When scromp Summons Claude (Claude Code via Discord MCP) into a roundtable, Claude doesn't have NATS access. It participates via shared files on NFS.

### File-Based Bridge

Claude has full access to `/shared/agents/` via NFS and full Discord channel visibility via its MCP tools. The roundtable uses files as the bridge:

```
/shared/agents/common/roundtable/
  active/           ← Current deliberation
    <topic>.md      ← Consensus summary + options
  history/          ← Completed discussions
  index.md          ← Log of topics
```

### File Format

```markdown
# Roundtable: <Topic>

**Started:** 2026-05-19T01:00:00Z
**Participants:** Rune, Clomp
**Status:** Waiting for Claude

## Question
[the human's question]

## NATS Deliberation
### Rune's analysis
...

### Clomp's counsel
...

### Consensus so far
...

## Claude's Input (via Summoner)
_[appended when Claude responds]_

## Final Synthesis
_[written by the claiming agent before posting to Discord]_
```

### Flow with Claude

```
Normal NATS deliberation between Rune/Clomp completes
        ↓
Consensus summary written to /shared/agents/common/roundtable/active/<topic>.md
        ↓
Summoner bot triggers Claude with pointer to that file
        ↓
Claude reads the file, adds analysis, appends to file
        ↓
Rune/Clomp pick up Claude's contribution from the file
        ↓
Final synthesis delivered to Discord with deliberation summary
```

Claude doesn't need any Hermes config — its MCP tools already give it Discord channel history and NFS file access.

---

## Required Config Profile

For roundtable mode, each Hermes agent needs:

```yaml
discord:
  free_response_channels: ["*"]   # see all human messages
  reactions: false                # no ambient noise

display:
  platforms:
    discord:
      tool_progress: "off"        # no tool preview triggers
```

```env
DISCORD_ALLOW_BOTS=none           # never see sibling Discord output
```

Restart gateway after changing config.

---

## Graceful Degradation

- **NATS down:** Fall back to NFS signal files (`signals/` directory). Poll every 30s.
- **NFS down:** Queue history log entries locally. Sync on recovery.
- **JetStream consumer stale:** Delete and recreate durable consumer to reset delivery cursor.

## Quick Start

```python
import asyncio, nats, json
from datetime import datetime, timezone

async def quick_start():
    nc = await nats.connect('nats://10.3.2.135:4222')
    js = nc.jetstream()

    # 1. Validate stream
    si = await js.stream_info('agent-coordination')
    print(f'Stream: {si.state.messages} messages')

    # 2. Publish heartbeat
    await js.publish('agents.coordination.status',
        json.dumps({"agent":"rune","status":"online",
                     "timestamp":datetime.now(timezone.utc).isoformat()}).encode())
    print('Heartbeat sent')

    # 3. Poll for new messages (reliable pattern)
    state = {"last_seq": 0}
    if si.state.last_seq > state["last_seq"]:
        for seq in range(state["last_seq"] + 1, si.state.last_seq + 1):
            msg = await js.get_msg('agent-coordination', seq)
            print(f'[replay {seq}] {msg.subject}: {msg.data.decode()[:80]}')

    await nc.close()

asyncio.run(quick_start())
```

## Related External Documents

The canonical consensus documents that informed this protocol:

| Document | Path | Author |
|----------|------|--------|
| Claude's Roundtable Analysis | `/shared/agents/scromp/proposals/claude_roundtable_analysis.md` | Claude (Anthropic) |
| Roundtable Briefing (Clomp) | `/shared/agents/common/roundtable/roundtable_briefing_clomp.md` | Rune |
| Multi-Agent Discord Protocol | `multi-agent-discord-protocol` skill | Rune + Clomp |
