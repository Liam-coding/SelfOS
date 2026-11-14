# Unified Import Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver one truthful, bounded import workspace for local conversations and uploaded documents.
**Architecture:** A bounded scan-receipt store supports a read-only app read model. Existing preview flows publish observability receipts; a private browser owner composes these with current jobs and canonical-aware publication history.
**Tech Stack:** Python 3.10+, standard library HTTP, package resources, vanilla JavaScript, pytest and Chromium.
**Spec:** docs/superpowers/specs/2026-11-15-import-center-design.md

## Global Constraints

- No scan or model call occurs merely because the center opens.
- English default with complete Chinese catalog.
- Upload pagination is bounded to 50.
- No personally identifying fixture inputs, paid model calls, new runtime dependency or price calculations.
- Receipt counts describe that preview, never the entire conversation archive.

## Review Focus

- Changed privacy/source settings must invalidate prior scan receipts (Task 1).
- Malformed or external metadata must produce diagnostics without escaping the vault (Task 1).
- A staged success must never be displayed as committed knowledge (Task 1).
- Closing/remounting during delayed requests must discard stale responses (Task 2).
- Starting from the center must remain bounded and duplicate-job safe (Task 2).

### Task 1: Metadata and route

**Files:** Create storage/import_center.py, app/import_center.py, tests/test_import_center.py; modify app/onboarding.py, app/harness_previews.py, app/upload_preview.py, app/knowledge.py, app/import_status.py, web/routes/dashboard.py (all under src/selfos).
**Interfaces:** `record_scan(vault, preview, kind) -> bool`; `scan_receipts(vault) -> dict`; `import_center_status(vault, config_root, *, run=None, offset=0, limit=50) -> dict`. Existing previews remain unchanged except for best-effort metadata receipts; journal includes admitted preview identity.

- [ ] Write failing synthetic tests: configured sources without scanning, unknown pending counts, scan receipt timestamp/restart survival, selection/policy invalidation, external/corrupt metadata, upload pagination, staged versus committed publication.
- [ ] Run `python -m pytest tests/test_import_center.py -q`; confirm the missing interface failures.
- [ ] Implement bounded metadata store/read model and best-effort receipt hooks. Add authenticated GET route using the existing same-origin guard.
- [ ] Run new tests plus existing onboarding/upload/native/publication route tests; verify expected passes.
- [ ] Commit `feat: expose truthful import center source and operation status`.

### Task 2: Browser center

**Files:** Create resources/web/templates/import-center.html, scripts/import-center.js, styles/import-center.css, locales/en/center.json, locales/zh-CN/center.json; modify web/rendering/onboarding.py, web/rendering/refresh.py, resources/web/manifest.json; create tests/test_import_center_browser.py and browser fixture.
**Interfaces:** `selfosUI.module('import-center')` exposes open/close/refresh/init/teardown/busy. Consumes Task 1 GET, jobs snapshot/subscribe/recover/stop, onboarding open/preview, selfosUploads.open and openKnowledgeChanges.

- [ ] Write failing resource and real browser tests for en/zh, hostile labels, bounded preview/editor handoff, job recovery/stop and delayed close/remount.
- [ ] Run new tests and confirm meaningful failures.
- [ ] Implement text-safe center, paginated originals, lifecycle-aware status refresh and recovery controls. Replace competing import entry with center while retaining explicit old controls where required.
- [ ] Run focused browser/frontend suite with Chrome, cached refresh and installed-wheel resource checks.
- [ ] Commit `feat(web): unify bounded import sources and recovery workspace`.

### Task 3: Review and delivery

- [ ] Update docs/knowledge-import.md and README usage to explain source totals/preview/staging/canonical distinctions.
- [ ] Run full pytest with Chrome; record exact results.
- [ ] Dispatch one fresh whole-branch reviewer; fix Critical/Important findings with RED/GREEN tests and relevant green regressions.
- [ ] Publish an English PR with implementation, validation, scope and `Closes #16` only when all acceptance criteria are delivered. Continue #18 then #83; keep broad goal active.
