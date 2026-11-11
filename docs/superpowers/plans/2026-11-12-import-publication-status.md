# Import publication status implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Implement #37: distinguish installed knowledge, saved extraction checkpoints and unpublished staging records, and provide deliberate resume/rebuild actions.

**Architecture:** Keep the canonical knowledge store unchanged. Persist small operation journals separately from canonical transactions, record lifecycle phase and terminal outcomes, and combine journals with contained staging snapshots in a read-only status projection. Reuse the authenticated settings endpoint and existing import actions; do not introduce a parallel job runner.

**Tech stack:** Python 3.10+, existing atomic JSON writes, browser JavaScript and packaged locale resources.

**Spec:** https://github.com/Liam-coding/SelfOS/issues/37

## Constraints

- No full real conversation scans or live model calls in validation. Preserve private vault, passwords, sources, backups and checkpoints.
- Preserve all five frozen acceptance files byte-for-byte. No automatic merge.
- Status reads must not trigger model requests, source scans, imports or recovery writes.
- Published counts describe canonical state only. Staging retained records are provisional, and candidate totals are not verified facts.
- Never sum record counts across staging operations: overlapping snapshots would inflate them.
- Do not claim old checkpoints are stopped/failed from timestamps, missing journals or zero counts.
- Compatibility with current settings and base snapshot is separate from exact source revalidation, which occurs on explicit resume.

## Review focus

- Journal-write failure must not turn successful canonical publication into reported failure or lose knowledge.
- Crash between install and journal update: canonical last_operation must take precedence over a stale running journal.
- Symlinked external staging/journal paths, corrupt JSON and invalid field shapes: expose bounded diagnostics without private text or escaping paths.
- Multiple historical operations and incompatible policies: report individually without suggesting all are resumable or summing duplicates.
- Process disappearance: only report interrupted when recorded process ownership is verified terminal; a stale file alone is insufficient.

## Task 1: Persist lifecycle and project truthful status

Files: create src/selfos/app/import_status.py; modify src/selfos/app/knowledge.py; create tests/test_import_publication_status.py.

- [x] Add synthetic failing tests for stop after first saved record, failed refinement, publication, crash-like stale journal, old unknown staging, incompatible settings/base, multiple operations, malformed JSON and escaping paths.
- [x] Run focused tests and confirm meaningful failures before implementation.
- [x] Persist operation ID, owner PID, start/update dates, mode, phase, terminal outcome, expected canonical hash, policy hash and contained checkpoint reference. No model replies, source text, paths outside vault or free-text exceptions in public metadata.
- [x] Track scanning, extracting, refining and publishing phases with stopped/failed/completed terminal results. Distinguish lifecycle from canonical publication and expose the interrupted phase.
- [x] Add a read-only status projection: published counts/operation, compatible unique checkpoint count, individual staging retained counts and status/phase/compatibility/limitations. Inspect PID liveness before declaring interruption. Keep legacy unknown state explicit.
- [x] Reconcile canonical publication evidence over stale journal data. Do not let journal diagnostic failure invalidate installed=true or canonical transactions.
- [x] Verify synthetic stop/resume uses cached extraction, preserves source bytes and publishes exactly once; test pending refine/rebuild and incompatible checkpoints.

## Task 2: Show publication boundary and deliberate actions

Files: modify src/selfos/web/rendering/knowledge.py and dashboard.py as needed; create src/selfos/resources/locales/en/import.json and zh-CN/import.json; add focused UI/HTTP tests.

- [x] Add failing tests for authenticated status responses and real JavaScript rendering/action behavior.
- [x] Render published versus saved/provisional counts visibly beside existing knowledge controls and within settings, with each operation separate. Explain that publication follows successful consolidation/refinement.
- [x] Show persistent stopped/failed/interrupted/unknown status and blocking phase; avoid raw private diagnostics. Provide explicit resume/rebuild buttons routed to existing import confirmation/actions. Never resume on page load.
- [x] Support English default, Chinese switch, loading/errors, keyboard and narrow screens. Dynamically rerender on language changes.
- [x] Refresh status after terminal import/stop and page load without source scan/model request; preserve current form edits.

## Task 3: Verify and deliver

- [x] Run focused service/HTTP/JavaScript tests, then full suite once changes stabilize.
- [x] Verify synthetic stopped-zero-published/nonzero-staged UI and resumed publication on desktop/mobile browser.
- [x] Verify packaged locale resources and all frozen hashes.
- [x] Submitted PR #42 with Closes #37 after independent reviews and verification.

Validation: 643 full tests passed, 23 focused regressions passed, and three UI
checks plus the production desktop/mobile Chromium fixture passed after final
styling. English/Chinese wheel resources and all five frozen acceptance hashes
were verified. No real source scan or live model calls were used.
