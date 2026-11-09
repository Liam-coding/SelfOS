# Vault

This is your personal knowledge base. Your AI reads these files at session start to understand your context.

## Root files

| File | Purpose |
|------|---------|
| `PROFILE.md` | Who you are — identity, role, skills, goals |
| `NOW.md` | What matters right now — priorities, active work, blockers |
| `GOALS.md` | Short and long-term goals with checkboxes |
| `DECISIONS.md` | Append-only decision log — never delete entries |
| `CLAUDE.md` | AI agent instructions — auto-loaded by Claude Code |

## Directories

| Directory | Purpose |
|-----------|---------|
| `01_Career/` | Career history, job opportunities, evaluation criteria |
| `02_Work/` | Active work projects, one file per project |
| `03_Research/` | Research projects, experiments, papers, hypotheses |
| `04_Health_Fitness/` | Training plans, logs, health data |
| `05_Life/` | Learning, side projects, relationships, housing |
| `06_Reviews/` | Weekly and monthly reviews |
| `07_World_Observer/` | External signals, reading notes, market intelligence |
| `90_Inbox/` | Raw AI session digests — **git-ignored**, treat as sensitive |
| `91_Staging/` | Proposed changes awaiting your approval |
| `98_Archive/` | Historical records no longer active |
| `99_Templates/` | Reusable templates for common file types |

## How to update

Your AI proposes changes to `91_Staging/` first. Review them, then say "apply" to write to canonical files. Nothing is committed without your approval.

To update your vault manually:
1. Edit any file directly
2. Run `git add vault/ && git commit -m "update: [what changed]"`
