# Workload and request budget implementation plan

Superseded for PR #66 by `2026-11-13-token-statistics.md`: the user deferred prices and workload prediction. The original plan below is retained as historical design context, not the current acceptance criteria.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Implement #22's bounded preview, request limits and measured usage.

**Architecture:** Read-only preview reuses source selection and compaction; durable transport journals count actual requests. Existing import settings and status endpoints expose the results.

**Tech Stack:** Python 3.10+, urllib, JSON, OS advisory locks, native JavaScript/CSS and locale catalogs.

**Spec:** docs/superpowers/specs/2026-11-13-workload-budget-design.md

## Global constraints

- No paid model requests or private source scans; use synthetic fixtures.
- 8 preview files, 8 MiB/file, 2000 entries; no preview writes.
- Default request limit 100, valid range 1..10000; English default and Chinese.
- Exclusions, source fingerprints, transaction boundaries and onboarding allowances remain authoritative.

## Review focus

- Missing/malformed provider usage stays unknown (Task 1).
- Concurrent workers and restart retain consumed quota (Task 1).
- Excluded and oversize sources never enter preview (Task 2).
- Cached parts do not imply free refinement (Task 2).
- Changing model config invalidates saved pricing and locale changes preserve form inputs (Task 3).

### Task 1: Durable request accounting

Files: storage/usage.py; app/budget.py; providers/client.py; tests/test_request_usage.py.
Interface: RequestUsage(vault, identity, limit, delegate=None), claim()->int, observe(ticket, data, provider), fail(ticket), status()->dict. read_budget/save_budget validate exact fields and model identity.

- [ ] Write real HTTP fixture tests proving three attempts consume a three-request allowance, fourth never reaches the server, restart retains it, concurrent claims do not overspend, usage is observed once, missing/cache usage remains unknown.
- [ ] Run pytest tests/test_request_usage.py -q and observe failure before implementing.
- [ ] Implement bounded contained journal I/O, advisory locking, validation and transport observation. Preserve existing SampleBudget protocol.
- [ ] Run focused transport tests; commit after passing.

### Task 2: Read-only preview and pipeline limits

Files: app/workload.py; app/knowledge.py; app/knowledge_status.py; tests/test_workload_preview.py; tests/test_knowledge_service.py.
Interface: workload_preview(vault, config_root)->dict; usage_status(vault, config_root)->dict. Pipeline creates RequestUsage after deriving checkpoint identity and passes it to provider factories; sample delegates enforce existing allowance.

- [ ] Write fixtures proving preview creates no files, respects exclusions/limits, distinguishes pending and cached parts, reports uncertain cost, and exhausted runs preserve canonical state and checkpoints.
- [ ] Observe failures, then implement. Snapshot current model pricing and policy; exact policy-augmented fingerprints determine reuse.
- [ ] Verify focused source/pipeline/transport tests; commit after passing.

### Task 3: Localized controls and progress

Files: web/routes/actions.py; web/routes/dashboard.py; resources/web/templates/import-controls.html; resources/web/scripts/import-controls.js; locales; docs/knowledge-import.md; tests/browser/workload.py.
Interfaces: authenticated GET /__knowledge_workload__, POST /__knowledge_budget__, usage data in /__knowledge_settings__.

- [ ] Write route/browser fixtures for authentication, active-job rejection, invalid budgets, unknown pricing, language changes and progress updates.
- [ ] Observe failures, implement controls and progress without triggering a model request on preview/save.
- [ ] Run full pytest, real fixture browser checks, installed resource checks and independent review. Create a PR linked to #22 after required evidence passes.
