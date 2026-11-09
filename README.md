# SelfOS

**Your personal operating system — structured memory + AI collaboration, works with any LLM.**

SelfOS is an open framework for building a personal knowledge and memory system that AI agents can read, update, and reason over. Think of it as the OS layer between you and your AI assistant — your second brain that persists across every conversation.

> "An AI that remembers nothing about you is a stranger. SelfOS turns it into a collaborator."

---

## What is this?

Most AI assistants forget you the moment the session ends. SelfOS fixes that by giving your AI a structured, version-controlled knowledge base about your life — your goals, career, health, research, decisions, and context.

- **Git-native**: everything is Markdown + Git. Your life has version history.
- **AI-agnostic**: works with Claude Code, Codex, or any agent that can read files.
- **Privacy-first**: runs entirely on your local machine. No cloud, no database.
- **Structured but flexible**: opinionated enough to be useful out of the box, open enough to adapt to your life.

---

## How it works

```
You ──→ AI Agent ──→ reads vault/ ──→ understands your context
                  ──→ proposes changes to 91_Staging/
                  ──→ you approve
                  ──→ applies to canonical files
                  ──→ commits to Git
```

The vault is a directory of Markdown files organized by life domain. The AI reads these files at the start of each session and maintains them over time. The staging workflow ensures nothing is written without your approval.

---

## Vault structure

```
vault/
├── PROFILE.md          # Who you are — identity, background, skills
├── NOW.md              # Current state — priorities, active projects, blockers
├── GOALS.md            # Short and long-term goals
├── DECISIONS.md        # Append-only decision log
│
├── 01_Career/          # Career history, opportunities, criteria
├── 02_Work/            # Active work projects and logs
├── 03_Research/        # Research projects, experiments, papers
├── 04_Health_Fitness/  # Training plans, logs, health data
├── 05_Life/            # Learning, relationships, housing, side projects
├── 06_Reviews/         # Weekly and monthly reviews
├── 07_World_Observer/  # External signals, market intelligence, reading
│
├── 90_Inbox/           # Raw input (git-ignored, treated as sensitive)
├── 91_Staging/         # Proposed changes awaiting approval
├── 98_Archive/         # Historical records
└── 99_Templates/       # Reusable templates
```

---

## Memory system

SelfOS includes a persistent memory layer for AI agents — a set of structured Markdown files the agent reads at session start to recall who you are, your preferences, and your ongoing work.

```
memory/
├── MEMORY.md           # Index of all memory files
├── user-profile.md     # Background, role, goals, preferences
├── feedback.md         # How you like to work with AI
└── project-context.md  # Current project state
```

Memory files use a simple frontmatter schema:

```yaml
---
name: user-profile
description: Background, role, and preferences — read before any advice
metadata:
  type: user  # user | feedback | project | reference
---
```

---

## Getting started

### 1. Clone and initialize

```bash
git clone https://github.com/Liam-coding/SelfOS.git
cd SelfOS
```

### 2. Fill in your profile

Edit `vault/PROFILE.md` and `vault/NOW.md` with your own information. These are the two files your AI will read most often.

### 3. Configure your AI agent

**Claude Code**: Copy `CLAUDE.md` to your vault directory. Claude Code will automatically load it as instructions.

**Other agents**: Point your agent at the vault directory and instruct it to read `PROFILE.md`, `NOW.md`, and the `memory/` directory at session start.

### 4. Start a session

Tell your AI:
> "Read my vault and memory files. Then help me update my goals."

The AI will read your context, propose changes to `91_Staging/`, and wait for your approval before writing anything.

---

## The staging workflow

SelfOS enforces a **propose → approve → apply → commit** workflow. No AI writes directly to canonical files.

1. AI reads existing files
2. AI proposes changes → writes to `91_Staging/YYYY-MM-DD-topic.md`
3. You review and say "apply"
4. AI applies changes to canonical files and commits

This means your vault is always in a state you consciously approved.

---

## Information classification

Every claim in the vault is labeled:

| Label | Meaning |
|-------|---------|
| `confirmed` | You stated it directly |
| `hypothesis` | Unverified, clearly labeled |
| `ai-inference` | AI interpretation — never promoted to fact |
| `historical-decision` | Past choice, preserved even if superseded |
| `time-series` | Dated measurements |

---

## Supported AI agents

| Agent | Status | Notes |
|-------|--------|-------|
| Claude Code | ✅ Native | `CLAUDE.md` auto-loaded as instructions |
| OpenAI Codex | ✅ Supported | Point at vault directory |
| Any file-reading agent | ✅ Compatible | Read `PROFILE.md` + `memory/` at session start |

---

## Philosophy

Your AI assistant should know you — not just what you said in the last message, but who you are, what you're working toward, and how you think. SelfOS is the infrastructure layer that makes that possible.

It's not a product. It's a pattern. Fork it, adapt it, make it yours.

---

## Contributing

PRs welcome. If you adapt SelfOS to a new AI agent or workflow, open a PR to add it to the supported agents table.

---

## License

MIT
