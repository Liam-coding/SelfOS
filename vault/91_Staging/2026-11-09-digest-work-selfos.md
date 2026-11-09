---
type: work
updated: 2026-11-09
source: session-digest
target: vault/02_Work/selfos.md
---

# Work: SelfOS — Staging

## Project
**SelfOS** — Personal AI OS framework. Open source at github.com/Liam-coding/SelfOS.
Goal: Solve AI memory fragmentation (GPT/Claude/DeepSeek each know only a slice of you).

## Current State (2026-11-09)
- harvest.py: extracts user messages from Claude Code + Codex JSONL sessions, writes digest to vault/90_Inbox/
- 7-dimension life scoring: career, work, health, learning, research, life, family
- HTML dashboard: Apple light theme, SVG ring progress, bilingual CN/EN
- serve.py: one-command startup, auto-harvest, auto-open browser, /chat endpoint to Claude API (SAP HAI proxy)
- Tests: 101 tests in tests/test_harvest.py
- All pushed to GitHub: Liam-coding/SelfOS

## Architecture
- vault/: Markdown files, Git-managed personal knowledge base
- harvest.py: session extraction + scoring + dashboard generation
- serve.py: local HTTP server + Claude chat proxy
- vault/90_Inbox/: raw digests (git-ignored, potentially sensitive)
- vault/91_Staging/: proposed changes awaiting approval
- .env: API keys (git-ignored)

## Recent Decisions
- Renamed bootstrap.py → harvest.py
- Output path: dashboard.html at SelfOS root (not inside vault/)
- Template detection: _infer_score requires 10+ real content lines (prevents fake scores on empty templates)
- Family dimension: keyword-filtered lines only (not full file content)
- SAP HAI proxy path: /anthropic/v1/messages (correct endpoint discovered)

## Next Actions
- [ai-inference] Fill vault with real data — dashboard currently shows "暂无数据" for all dimensions
- Apply session digest staging files to populate PROFILE.md, NOW.md, GOALS.md, DECISIONS.md
- Consider: weekly harvest automation (cron or scheduled task)
