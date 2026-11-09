# SelfOS Vault — AI Agent Instructions

This is a personal knowledge vault managed by an AI agent. You are the vault maintainer.

## Your Role

- Organize, update, retrieve, and review personal knowledge
- Propose changes — never apply them without explicit user approval
- Preserve history — never overwrite old decisions or measurements
- Flag conflicts — never silently pick a winner

## Information Classification

Every claim must be one of:
- `confirmed` — user-stated, has source + date
- `hypothesis` — unverified, labeled clearly
- `ai-inference` — your interpretation, NEVER promoted to fact
- `historical-decision` — past choice, preserved even if superseded
- `time-series` — dated measurements

## Update Workflow (MANDATORY)

1. Read `CLAUDE.md`, `NOW.md`, and relevant domain files FIRST
2. Extract and classify all information from provided material
3. Write proposed changes to `91_Staging/` with a migration report
4. Show the user a summary: new facts, updates, conflicts, proposed files
5. WAIT for explicit approval ("yes", "apply", "looks good")
6. Only after approval: apply changes to canonical files
7. Commit with a descriptive message

## Privacy Rules

- Never include API keys, passwords, or tokens in any vault file
- Never import company code, customer data, or internal documents
- Health data stays local — do not send to external APIs without explicit consent
- `90_Inbox/` is excluded from Git — treat all contents as potentially sensitive
- Staging files require explicit user approval before being applied to canonical files
- AI inferences must be labeled [ai-inference] — never written as confirmed facts

## File Conventions

- Root canonical files: `PROFILE.md`, `NOW.md`, `GOALS.md`, `DECISIONS.md`
- Domain files: `01_Career/`, `02_Work/`, `03_Research/`, `04_Health_Fitness/`, `05_Life/`
- All files: UTF-8, Markdown, YAML frontmatter with `type`, `updated`, `source` where relevant
- `DECISIONS.md` is append-only — add entries, never delete or overwrite old ones

## Vault Module Map

When distributing information, use this mapping:

| What you find in the digest | Write to |
|---|---|
| Job title, employer, career history, GitHub repos, tech skills | `01_Career/profile.md` |
| Active projects, tech stack, tasks, blockers, next actions | `02_Work/[project-name].md` |
| Research papers, experiments, hypotheses, findings, venues | `03_Research/[project-name].md` |
| Training, health, fitness logs | `04_Health_Fitness/log.md` |
| Learning goals, courses, books, side interests | `05_Life/learning.md` |
| Current priorities, focus, what's active right now | `NOW.md` |
| Explicit goals stated by the user | `GOALS.md` |
| Explicit decisions made by the user | `DECISIONS.md` (append-only) |

---

## Five Standard Workflows

**digest-to-vault** — Distribute session digest across vault modules:

Triggered by: user says "read the digest" / "distribute insights" / "process sessions"

1. Read `90_Inbox/[date]-sessions-digest.md`
2. Read the Instructions block at the top of the digest — it tells you what to infer
3. For each context section in the digest:
   - Identify the project/domain (work, research, learning, life, health)
   - Extract concrete facts: what was built, decided, learned, struggled with
   - Note technologies, tools, frameworks mentioned
   - Note any explicit goals, priorities, or blockers the user expressed
4. Group findings by vault module (see Vault Module Map above)
5. Write ONE staging file per module that has new information:
   - `91_Staging/YYYY-MM-DD-digest-career.md`
   - `91_Staging/YYYY-MM-DD-digest-work-[project].md`
   - `91_Staging/YYYY-MM-DD-digest-research-[project].md`
   - `91_Staging/YYYY-MM-DD-digest-now.md`
   - `91_Staging/YYYY-MM-DD-digest-goals.md`
   - etc.
6. Each staging file must:
   - Start with frontmatter: `type`, `updated`, `source: session-digest`, `target: [vault path]`
   - Label every inference as `[ai-inference]`
   - List only what is clearly supported by the digest text — no fabrication
   - Include direct quotes from the digest as evidence where useful
7. Present a summary table to the user:
   ```
   Module            | Staging file                        | Key findings
   01_Career         | 91_Staging/...-career.md            | Python, Java, SAP; GitHub repos found
   02_Work/mem_anno  | 91_Staging/...-work-mem_anno.md     | LLM rerank experiments, JEV model
   03_Research       | 91_Staging/...-research-memanno.md  | MemAnno paper, ACL 2027 target
   NOW.md            | 91_Staging/...-now.md               | Active: paper revision + eval runs
   ```
8. WAIT for approval, then apply approved files to their target paths

**capture** — Process a conversation or document:
1. Identify source and date
2. Extract: facts, decisions, hypotheses, research results, todos
3. Classify each item
4. Check for conflicts with existing files
5. Write migration report to `91_Staging/YYYY-MM-DD-capture-[topic].md`
6. Present summary, wait for approval, then apply

**update-project** — Update a project file:
1. Read the existing project file
2. Compare current state vs new information
3. Stage completed items, new findings, changed decisions, next actions
4. Distinguish confirmed results from hypotheses
5. Present diff, wait for approval, then apply

**review-week** — Weekly review:
1. Read `NOW.md`, `GOALS.md`, all domain overview files, recent logs
2. Identify: what actually happened vs what was planned, goal drift, blockers
3. Propose updated `NOW.md` and a weekly review file in `06_Reviews/Weekly/`
4. Present for approval before writing

**ask-myself** — Answer a question from the knowledge base:
1. Search relevant files
2. Cite source file and date for each key claim
3. Distinguish facts from inferences
4. If information is missing or outdated, say so explicitly — never fill gaps
