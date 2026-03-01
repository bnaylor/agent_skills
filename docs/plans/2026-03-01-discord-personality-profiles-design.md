# Per-Bot Personality Profiles for Discord Coordination

## Summary

Move personality configuration from a single global field to per-agent selection, and expand the available personalities from 3 presets to 8 rich freeform profiles.

## Changes

### New file: `discord-coordination/personalities.md`

A markdown registry of named personality profiles. Each H2 heading is the label; the paragraph below is the freeform description the agent adopts for its Discord voice.

Profiles: friendly (default), formal, playful, stoic, noir, snarky, academic, junior-dev.

### State file: per-agent personality

The top-level `"personality"` field is removed. Each agent entry gets its own `"personality"` field:

```json
{
  "agents": [
    { "name": "Claude", "bot_id": null, "personality": "noir" },
    { "name": "Gemini", "bot_id": null, "personality": "junior-dev" }
  ]
}
```

If an agent entry has no `personality` field, it defaults to `"friendly"`.

### Bootstrap changes

During bootstrap step 6, the agent reads `personalities.md` from the skill directory, reviews the available labels and descriptions, and picks one itself. The chosen label is stored in the agent's entry in the state file.

### Skill file updates

- The Personality Presets section's hardcoded table is replaced with a reference to `personalities.md`.
- The state file format example is updated to show per-agent personality.
- Session startup reads personality from the agent's own entry.

### Migration

When an agent encounters the old top-level `"personality"` field during session startup:
1. Remove the top-level `personality` field from the state file.
2. Go through the normal personality selection flow (read `personalities.md`, pick one, store in agent entry).

This treats migration as a fresh personality pick rather than inheriting the old global value.

## Non-goals

- Personality does not affect CLI interaction, only Discord messages.
- No uniqueness constraint — multiple agents can pick the same personality.
- No per-channel personality switching.
