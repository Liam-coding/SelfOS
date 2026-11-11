# Project timelines implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Implement #19 with a traceable chronology of project goals, decisions, progress and blockers alongside authoritative current state.

**Architecture:** Build a read-only projection from canonical cards, their state/decision lineage and saved summaries. Reuse registered source navigation and authenticated knowledge endpoints; no additional history store, source scan or model call. New packaged locale resources and a focused timeline browser module integrate with project details.

**Tech stack:** Existing Python packages, browser JavaScript, packaged en/zh-CN JSON, synthetic pytest and authenticated browser fixtures.

**Spec:** https://github.com/Liam-coding/SelfOS/issues/19

## Constraints and design decisions

- Preserve private data, all five frozen acceptance files, backups and checkpoint formats. No real conversation scans or model calls.
- Current state is the canonical card, never the last timestamped timeline event. Show historical observations separately; a different goal is not proof of supersession. Explicit lifecycle metadata may identify supersession, otherwise disclose uncertainty.
- Use existing opaque project record IDs at the HTTP boundary, never expose absolute project/source paths. Alias resolution must follow canonical project aliases.
- Keep event time, source/session time and import time separate. Only explicitly recorded event/import dates may populate those fields; observed_at and updated_at are observation/session dates, not inferred event dates. Malformed/unknown dates remain unknown. Project-context legacy observations have unknown direct observation dates.
- Chronological order uses explicit event time where known, then observation/source time. Identify the ordering basis on each entry. Put undated entries in a separate group with stable identity ordering. Tied different snapshots remain visible without an insertion-order winner.
- Use state_inputs where present to retain individual episodes, then state_records and conservative legacy fallback. Saved summaries preserve goals and session-specific decisions; decision lineage adds coverage absent from summaries. Deduplicate equivalent same-source observations without discarding differing source support or ambiguous time.
- Entries expose type, redacted content, attribution, source scope, dates, source metadata and unavailable source count. Reuse allowed-root and matching-message verification for original conversations. Context evidence must not be displayed as an exact quote.
- Filter all/goals/decisions/progress/blockers; pagination is bounded and deterministic. Current summary stays visible independently of filters. Restores and canonical edits must invalidate the read projection; do not retain stale parallel copies.
- English default and Chinese resources; accessible buttons, keyboard dialog, mobile layout, safe DOM text rendering and stale-response protection. Add timeline entry from project record detail and refresh cached dashboard integration without persisting generated HTML.

## Review focus

- Late-arriving snapshots, equal timestamps and repeated states: coherent ordering without invented resolution.
- Changed goals, decisions and blockers: current versus historic labels reflect canonical data, not guessed supersession.
- Missing or malformed lineage/source metadata, alias identities and project-context legacy dates: explicit uncertainty and no cross-project leakage.
- Canonical edits/restores and pagination between reads: no stale history cache or silent missing sources.
- Language changes, delayed HTTP results and literal HTML evidence: preserved filters, safe text and retryable errors.

## Task 1: Pure chronology projection

Files: create src/selfos/knowledge/timeline.py and tests/test_project_timeline.py.

Interface: project_timeline(state, project_id) returns current summary plus stable entries with type/text/status/blockers/next_steps, event_time/observed_at/source_times/imported_at, ordering basis, source_ids/scope/attribution and lifecycle markers. Never mutates state.

- [x] Write failing fixtures for three sessions with changing goals/blockers/decisions, late arrival, equal timestamps, legacy unknown dates, deduplication, aliases and source attribution.
- [x] Run tests and inspect expected missing-capability failures.
- [x] Implement the pure projection and conservative date/lifecycle handling.
- [x] Run focused history/project regression tests and add missing malformed-input cases.

## Task 2: Authenticated API and source navigation

Files: modify src/selfos/app/library.py and src/selfos/web/routes/dashboard.py; create tests/test_auth_project_timeline.py.

Interface: knowledge_timeline(vault, identity, category=all, offset=0, limit=50) resolves an existing project record ID, returns current plus paginated entries and redacted registered source metadata. GET /__knowledge_timeline__ uses id/category/offset/limit.

- [x] Write failing authentication/cross-site, pagination/filter, unknown/nonproject identity, missing-source and canonical restore/edit tests.
- [x] Implement read-only API and route with consistent validation and errors.
- [x] Verify no source scans/model requests and existing source restrictions remain enforced.

## Task 3: Timeline UI and release verification

Files: create src/selfos/web/rendering/timeline.py, packaged locales en/timeline.json and zh-CN/timeline.json, tests/test_project_timeline_ui.py and docs/project-timelines.md; integrate in library rendering and authenticated dashboard refresh; update both READMEs.

- [x] Write failing JavaScript/browser contract tests for project entry, filters, dates/uncertainty, source navigation, safe text, pagination retries and stale responses.
- [x] Implement responsive localized current-state/timeline view with source links and unknown-date group.
- [x] Verify actual authenticated synthetic desktop/mobile dashboard, both languages, sources, keyboard and no overflow.
- [x] Run focused and full suites, wheel resources and all frozen hashes; obtain skill-required independent review and fix findings.
- [x] Create a separate English PR with Closes #19 after verification; do not auto-merge.


## Verification and review

Final full suite: 643 passed in 95.56s. Focused independent final review: 23 passed; all important findings fixed through failing regression tests. Actual authenticated generated-dashboard checks passed at desktop/mobile widths in English and Chinese, including original sources, filter retention, keyboard dismissal and literal HTML text. Built wheel imports and both locale resources verified; all five frozen acceptance hashes unchanged. Revision-aware pagination restarts on canonical changes. Uncovered legacy decisions remain undated; aggregated decision lineage adds residual support only. No private data changes or live model/source scans.
