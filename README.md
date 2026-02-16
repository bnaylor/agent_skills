# Agent Skills

A collection of skills for AI coding agents (Claude Code, etc.). Each skill is a self-contained protocol that teaches an agent how to perform a specific operational task.

## Skills

### [discord-coordination](discord-coordination/SKILL.md)

Enables AI agents to use Discord as a communication channel — posting status updates, receiving instructions from humans, and coordinating with other agents. Handles bootstrap, session startup, message protocols, multi-agent conflict avoidance, and personality presets.

### [microk8s-janitor](microk8s-janitor/SKILL.md)

Automates rolling upgrades and maintenance for HA MicroK8s clusters over SSH. Discovers cluster topology from a single seed node, runs pre-flight health checks, and performs sequential cordon/drain/upgrade/uncordon cycles with stateful recovery on failure.

## Usage

These skills are designed to be loaded by AI agents that support skill/instruction files. To use a skill:

1. Point your agent's skill configuration at the relevant `SKILL.md` file.
2. The agent will follow the protocol defined in the skill when the activation conditions are met.

For Claude Code, skills can be installed via the [superpowers](https://github.com/anthropics/superpowers) framework or loaded directly.

## Structure

```
<skill-name>/
  SKILL.md          # The skill definition (frontmatter + protocol)
docs/
  plans/            # Design documents and specs
```

## License

MIT
