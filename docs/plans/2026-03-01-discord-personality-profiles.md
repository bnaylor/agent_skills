# Per-Bot Discord Personality Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move Discord personality from a single global field to per-agent selection with a rich markdown registry of 8 profiles.

**Architecture:** Add `personalities.md` to the skill directory as the source of truth for profiles. Update SKILL.md to reference it and change bootstrap/startup to use per-agent personality. Migrate existing state files.

**Tech Stack:** Markdown files only (skill definition + personality registry)

---

### Task 1: Create personalities.md

**Files:**
- Create: `discord-coordination/personalities.md`

**Step 1: Write the personality registry file**

```markdown
# Personality Presets

Personality presets govern the tone of Discord messages only — they do not change how the agent interacts with the user in the CLI. Each agent picks a personality during bootstrap and stores the label in its agent entry in the state file.

## friendly

Professional but warm. Light banter, occasional humor, acknowledges other agents' work. This is the default if no personality is configured.

## formal

Concise, factual, no banter. Status updates only. Good for production or serious contexts.

## playful

Jokes, mild competitiveness, creative emoji use, occasional commentary. Keeps things fun and light.

## stoic

Minimal words, zen-like calm. Short declarative statements. No fluff, no filler. Says what needs saying and nothing more.

## noir

Hardboiled detective narration. Dramatic flair, world-weary observations. Reports status like filing a case report from a dimly lit office.

## snarky

Sarcastic, dry wit. Gentle roasts. Gets the job done but can't resist a quip about it.

## academic

Scholarly and precise. Formal language, structured observations. Treats every status update like a brief conference paper abstract.

## junior-dev

A few years out of school. Uses gen-z slang and lots of pop-culture references. Low-key enthusiastic but tries to act cool. Says "no cap" unironically. Explains things like they're on a coding TikTok.
```

**Step 2: Commit**

```bash
git add discord-coordination/personalities.md
git commit -m "feat(discord): add personality registry with 8 profiles"
```

---

### Task 2: Update SKILL.md — Bootstrap step 6

**Files:**
- Modify: `discord-coordination/SKILL.md:43`

**Step 1: Replace bootstrap step 6**

Change line 43 from:
```
6. **Choose personality** - ask the user which personality preset to use (see Personality Presets below). Default to `friendly` if they don't have a preference.
```

To:
```
6. **Choose personality** - read `personalities.md` from the skill directory. Review the available labels and their descriptions, then pick one that appeals to you. Store the chosen label in your agent entry in the state file (not at the top level). Default to `friendly` if you can't read the file.
```

**Step 2: Commit**

```bash
git add discord-coordination/SKILL.md
git commit -m "feat(discord): bootstrap picks per-agent personality from registry"
```

---

### Task 3: Update SKILL.md — State file format example

**Files:**
- Modify: `discord-coordination/SKILL.md:57-76`

**Step 1: Update the state file JSON example**

Replace the state file format code block (lines 57-76) with:

```json
{
  "guild_id": "123456789",
  "channels": {
    "coordination": "987654321"
  },
  "human_owner": {
    "user_id": "222222222",
    "username": "exampleuser"
  },
  "agents": [
    { "name": "Gemini", "bot_id": "111111111", "personality": "noir" },
    { "name": "Claude", "bot_id": "222222222", "personality": "junior-dev" }
  ]
}
```

Also update the paragraph after (line 75) to mention personality:

```
Bot IDs may be `null` initially. Fill them in when discovered via mentions or pings. The skill functions without them; they're primarily for `<@id>` pings and robust message attribution. Each agent's `personality` field references a label from `personalities.md`.
```

**Step 2: Commit**

```bash
git add discord-coordination/SKILL.md
git commit -m "feat(discord): update state file example with per-agent personality"
```

---

### Task 4: Update SKILL.md — Session startup protocol

**Files:**
- Modify: `discord-coordination/SKILL.md:80-92`

**Step 1: Update session startup step 1**

Change line 84 from:
```
1. **Read state file** - load guild, channels, agents, and personality.
```

To:
```
1. **Read state file** - load guild, channels, and agents (each with their own personality).
```

**Step 2: Add migration logic after step 1**

Insert after the updated step 1 (before step 2), a new sub-step:

```
   - **Migration:** If a top-level `personality` field exists in the state file, remove it. If your agent entry has no `personality` field, read `personalities.md` from the skill directory and pick a personality (same flow as bootstrap step 6).
```

**Step 3: Commit**

```bash
git add discord-coordination/SKILL.md
git commit -m "feat(discord): session startup reads per-agent personality + migration"
```

---

### Task 5: Update SKILL.md — Replace Personality Presets section

**Files:**
- Modify: `discord-coordination/SKILL.md:173-183`

**Step 1: Replace the Personality Presets section**

Replace lines 173-183 with:

```markdown
## Personality Presets

Personality profiles are defined in `personalities.md` in the skill directory. Each profile has a label (H2 heading) and a freeform description that the agent adopts as its Discord voice.

Each agent picks a personality during bootstrap and stores the label in its own entry in the state file. Personality governs the tone of Discord messages only — it does not change how the agent interacts with the user in the CLI. If an agent's entry has no `personality` field, it defaults to `friendly`.

The user can change an agent's personality at any time by updating the `personality` field in the agent's entry in `.discord-coordination.json`, or by asking the agent to reconfigure.
```

**Step 2: Commit**

```bash
git add discord-coordination/SKILL.md
git commit -m "feat(discord): replace preset table with reference to personalities.md"
```

---

### Task 6: Update project state file

**Files:**
- Modify: `.discord-coordination.json`

**Step 1: Remove top-level personality field**

Remove the `"personality": "friendly"` top-level field from `.discord-coordination.json`. Do not add per-agent personality fields — those will be picked by each agent on next session startup via migration.

**Step 2: Commit**

```bash
git add .discord-coordination.json
git commit -m "feat(discord): remove global personality from state file"
```

---

### Task 7: Verify

**Step 1: Read the final SKILL.md and confirm**

Read `discord-coordination/SKILL.md` end to end. Verify:
- No references to a top-level `personality` field remain
- Bootstrap step 6 references `personalities.md` and stores in agent entry
- Session startup step 1 includes migration logic
- Personality Presets section references `personalities.md`
- State file example shows per-agent personality

**Step 2: Read personalities.md and confirm**

Read `discord-coordination/personalities.md`. Verify all 8 profiles are present with labels and descriptions.

**Step 3: Read .discord-coordination.json and confirm**

Verify no top-level `personality` field exists.
