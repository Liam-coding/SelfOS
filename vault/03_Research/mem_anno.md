---
type: research
updated: 2026-11-09
source: session-digest
---

# Research: MemAnno

## Project Overview
**MemAnno** — Long-term memory system via structured cue annotation.
Core idea: paragraphs are never modified; cues are the retrieval index.
Direction: context compression + structured memory retrieval for LLMs.
Repo: github.com/Liam-coding/mem_anno

## Architecture (current)
- CueStore: stores cue annotations per paragraph
- Retrieval pipeline: BM25 + embedding + optional rerank layers
- Jev rerank: N serial API calls, one per candidate paragraph; input = cue summary; output = score float
- LLM rerank: one API call, numbered list of summaries → JSON array of selected indices
- `_build_cue_summary()`: enriched text from cue fields: `"object (time, place, attitude) | triggers: t1, t2"`

## Current Best Config
- Config B: No time-intent layer + Instruct prefix + top-10 + Jev full rerank
- F1 = 0.6109 on LoCoMo (1540 questions)

## Active Branch: feature/rerank-jev-triggers
- Added `query_triggers` to `_build_cue_summary()` for richer Jev rerank input
- Pushed to Liam-coding/mem_anno
- Tests: 37 tests in tests/test_cue_summary.py

## Active Experiments (as of 2026-11-09)
- Running LoCoMo eval on feature/rerank-jev-triggers vs baseline F1 0.6109
- Comparing: gpt-4.1-mini full+Jev, full+Jev+adaptive-k
- Partial results: F1 0.435–0.463 (smaller sample — conv subset, not full 1540 yet)
- Some eval failures: conv-48 Jev getaddrinfo errors (network issue with model server)

## Research Questions Being Explored
- Does adding query_triggers to cue summary improve retrieval F1?
- How to handle temporal knowledge evolution (e.g., person's view changes 2020→2021→2022)?
- Is delete_cue() (physical deletion + embedding rebuild) resource-intensive? [ai-inference: yes, O(n) rebuild]
- Can context compression approach apply to coding agent tasks (SWE-bench)? [exploratory]

## Next Paper Target
- Modified/extended MemAnno as next paper (decided 2026-10-16)
- Target venue: [ai-inference] ACL/EMNLP/ICLR tier
- Status: experiments in progress; paper revision after eval results
