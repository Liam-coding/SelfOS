---
name: digest
description: >
  Use this skill when the user says "/digest", "process my sessions",
  "read the digest", "distribute insights", or "update vault from sessions".
  Reads the latest session digest from vault/90_Inbox/ and distributes
  insights across vault modules via the staging workflow.
allowed-tools: Read, Write, Bash, Glob
---

# digest — Distribute Session Insights to Vault

## What this does

Reads your latest session digest (written by `harvest.py`) and distributes
what it learns about you across the vault modules where it belongs:
career, work, research, goals, decisions, and current priorities.

Nothing is written without your approval.

---

## Step 1 — Find the latest digest

```bash
ls vault/90_Inbox/ | sort | tail -5
```

Read the most recent `*-sessions-digest.md` file.

If no digest exists, tell the user:
> "No digest found. Run `python -m selfos harvest` first, then come back."
> Stop here.

---

## Step 2 — Read existing vault state

Before writing anything, read:
- `vault/NOW.md`
- `vault/GOALS.md`
- `vault/PROFILE.md` (if exists)

This prevents overwriting what's already confirmed.

---

## Step 3 — Analyze the digest

Work through every context section in the digest. For each one, extract:

| What you find | Where it goes |
|---|---|
| Job title, employer, tech skills, GitHub repos | `01_Career/profile.md` |
| Active projects, stack, tasks, blockers, next actions | `02_Work/[project].md` |
| Research papers, experiments, hypotheses, results, venues | `03_Research/[project].md` |
| Training, health, fitness | `04_Health_Fitness/log.md` |
| Learning goals, courses, books | `05_Life/learning.md` |
| Current priorities, what's active now | `NOW.md` |
| Explicit goals the user stated | `GOALS.md` |
| Explicit decisions the user made | `DECISIONS.md` (append-only) |

Rules:
- Label every inference `[ai-inference]`
- Only write what is clearly supported by the digest text
- Do not fabricate or extrapolate beyond what was said
- Include a short quote from the digest as evidence for each key claim

---

## Step 4 — Write staging files

Write one file per module that has new information.

File naming: `vault/91_Staging/YYYY-MM-DD-digest-[module].md`

Each file starts with:
```yaml
---
type: [career | work | research | goals | now | decisions | life | health]
updated: YYYY-MM-DD
source: session-digest
target: vault/[path to canonical file]
---
```

---

## Step 5 — Present summary and wait

Show the user a table before touching anything:

```
Module             | File                                   | Key findings
-------------------|----------------------------------------|---------------------------
01_Career          | 91_Staging/...-digest-career.md        | [2-3 word summary]
02_Work/[project]  | 91_Staging/...-digest-work-[proj].md   | [2-3 word summary]
03_Research        | 91_Staging/...-digest-research-....md  | [2-3 word summary]
NOW.md             | 91_Staging/...-digest-now.md           | [2-3 word summary]
```

Then say:
> "Review the staging files above. Say **apply** to write them to the vault, or tell me what to change."

**Do not apply anything until the user explicitly approves.**

---

## Step 6 — Apply and commit

After approval:
1. Apply each staging file to its `target` path
2. Commit with message: `digest: distribute session insights YYYY-MM-DD`
