# Agent Integration Guide

SelfOS is AI-agnostic. This guide explains how to connect different agents to your vault.

## Claude Code (default)

Claude Code auto-loads `CLAUDE.md` from the vault directory as instructions.

1. Copy or symlink `vault/CLAUDE.md` into your vault root
2. Open Claude Code in the `vault/` directory
3. Claude will automatically read your context and follow the staging workflow

**Memory system**: Copy the `.claude/` config from this repo and point it at your `memory/` directory.

## OpenAI Codex / GPT-based agents

Add this system prompt prefix to your agent:

```
You are a personal knowledge assistant. At the start of every session:
1. Read vault/PROFILE.md and vault/NOW.md
2. Read all files in memory/
3. Follow the staging workflow in vault/CLAUDE.md — never write directly to canonical files

Your working directory is: [path to your SelfOS vault]
```

## Any file-reading agent

The minimum required context for any agent:
- `vault/PROFILE.md` — who the user is
- `vault/NOW.md` — what's happening right now
- `memory/MEMORY.md` + linked files — persistent memory
- `vault/CLAUDE.md` — behavioral rules and workflows

Point your agent at these files and instruct it to propose changes to `vault/91_Staging/` rather than editing canonical files directly.

## Adding a new agent

1. Test the agent with the minimum required context above
2. Document any agent-specific config in this file
3. Open a PR documenting the integration here and updating the README's agent setup guidance
