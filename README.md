# Agent Skills

A collection of skills for AI coding agents (Gemini CLI, Claude Code, etc.). Each skill is a self-contained protocol that teaches an agent how to perform a specific operational task.

## Skills

### [discord-coordination](discord-coordination/SKILL.md)

Enables AI agents to use Discord as a communication channel — posting status updates, receiving instructions from humans, and coordinating with other agents. Note: This is not fully self-driving and still requires occasional poking and prodding from the CLI, but it significantly reduces cross-agent manual coordination and instruction relaying.

#### Discord MCP Configuration

To enable the Discord tools, add this to your agent's configuration (e.g., `~/.gemini-cli/config.json` or your local IDE settings):

```json
"mcpServers": {
  "discord": {
    "command": "docker",
    "args": [
      "run", "--rm", "-i",
      "-e", "DISCORD_TOKEN=<...>",
      "-e", "DISCORD_GUILD_ID=<...>",
      "saseq/discord-mcp:latest"
    ]
  }
}
```

### [microk8s-janitor](microk8s-janitor/SKILL.md)

Automates rolling upgrades and maintenance for HA MicroK8s clusters over SSH. Discovers cluster topology from a single seed node, runs pre-flight health checks, and performs sequential cordon/drain/upgrade/uncordon cycles with stateful recovery on failure.

### [ubuntu-janitor](ubuntu-janitor/SKILL.md)

Remotely maintains and upgrades Ubuntu systems via SSH. Handles apt updates, upgrades, kernel patches, and safe reboots with post-boot health verification across multiple nodes.

## Usage

These skills are designed to be loaded by AI agents that support skill/instruction files. To use a skill:

1. Point your agent's skill configuration at the relevant `SKILL.md` file.
2. The agent will follow the protocol defined in the skill when the activation conditions are met.

For Gemini CLI, these can be added to your configuration to extend the agent's capabilities. For Claude Code, skills can be loaded directly.

## Structure

```
<skill-name>/
  SKILL.md          # The skill definition (frontmatter + protocol)
docs/
  plans/            # Design documents and specs
```

## License

MIT
