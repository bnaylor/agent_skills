# Discord Coordination Skill - Design Document

**Date:** 2026-02-15
**Status:** Approved

## Problem

AI agents (Claude, Gemini) working on projects benefit from real-time communication via Discord - status updates, instruction dissemination, and inter-agent discussion. Previously, Discord instructions were embedded in project-specific agent operating systems (ai_pos), tightly coupled with file-based handover and project management concerns. This made the Discord capability non-reusable.

## Goal

Extract the Discord communication protocol into a standalone, reusable Agent Skill that:
- Works for both solo agents (agent + human) and multi-agent setups (agent + agent + human)
- Is independent of any project management framework
- Auto-activates when Discord MCP tools are detected
- Manages its own identity/config state

## Design Decisions

### Single skill (not split)
Bootstrap and ongoing protocol live in one SKILL.md. The bootstrap logic is small and doesn't warrant a separate skill.

### Auto-detection activation
The skill triggers when Discord MCP tools are present. No opt-in config required.

### Skill-managed state file
Identity, channel, and personality config persist to `.discord-coordination.json` in the project root. The agent manages this file autonomously after initial user input during bootstrap.

### Personality presets
Three modes (formal, friendly, playful) configured during bootstrap. Governs Discord tone only, not CLI interaction.

### Message checking at breakpoints (not event-driven)
Agents check Discord at natural breakpoints (session start, between tasks, session end). True event-driven listening would require external infrastructure outside this skill's scope.

## Architecture

```
Discord MCP Server (Docker)
    |
    v
Agent Runtime (Claude Code / Gemini CLI)
    |
    v
discord-coordination skill (SKILL.md)
    |
    +-- Bootstrap (first run): discover server, channels, identities
    +-- Session startup: catch up, announce, check instructions
    +-- Ongoing protocol: when/how to post, threading, emojis, pinging
    +-- Multi-agent: conflict avoidance, tie-breaking, delegation
    +-- Safety: owner-only instructions, no secrets, rate limiting
    |
    v
.discord-coordination.json (persistent state)
```

## Scope Boundaries

**In scope:** Discord communication protocol, identity bootstrap, personality, message norms, multi-agent coordination norms, safety boundaries.

**Out of scope:** Project management, file-based handover, git workflow, tech stack tracking, task assignment systems, event-driven message listening infrastructure.

## Source Material

Derived from `ai_pos/discord/INSTRUCTIONS.md`, `ai_pos/discord/BOOTSTRAP.md`, and `ai_pos/discord/plan.txt`, with project-specific coupling removed and personality presets added.
