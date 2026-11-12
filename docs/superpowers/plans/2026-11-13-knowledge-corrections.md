# Durable knowledge corrections implementation plan

> **For agentic workers:** use superpowers:executing-plans inline. Follow test-driven-development for each task.

**Goal:** implement #15 edit/delete/merge/undo while retaining source evidence and honoring corrections after imports/rebuilds.

**Architecture:** separate durable action ledger from generated state; pure overlay replay for views/context/Markdown; authenticated transaction service uses existing vault lock, atomic journal and backups.

**Tech Stack:** Python standard library, packaged JavaScript/CSS, existing i18n catalogs, pytest and synthetic Chromium checks.

**Spec:** docs/superpowers/specs/2026-11-13-knowledge-corrections-design.md

## Global constraints

- No original conversation edits, private vault reads or real model calls.
- Source quotations support original generated claims, never fabricated manual edits.
- Corrections remain sticky by relation/scope; new evidence is visible conflict.
- Undo refuses active dependencies; never restores old state over later imports.
- Existing local/auth protections, UTC times, size limits, English default and Chinese localization.

## Review focus

- Changed key/text with unchanged evidence must not recreate a suppressed lineage.
- Aggregates mixing suppressed and new evidence retain new evidence without hiding conflicts.
- Dependent actions cannot be silently lost through undo.
- Multiple app views and managed exports must use the same overlay.
- Stale browser versions and interrupted transactions must not apply partial changes.

### Task 1: pure ledger and overlay

Create src/selfos/knowledge/corrections.py; test tests/test_knowledge_corrections.py.

Interfaces: apply_corrections(state: dict, ledger: dict) -> dict; create_action(state: dict, ledger: dict, request: dict) -> dict. Ledger version=1, actions list. Actions edit/delete/merge/undo, each with unique id, UTC time, anchors, original versions and dependencies. Browser version IDs use the current record identity; anchor uses original category and exact source/quotation signatures plus relation/scope. Generated state is never mutated.

- [x] Write replay/edit/delete/merge/undo tests asserting source bytes unchanged, manual attribution, equivalent evidence suppression and active dependency rejection.
- [x] Run pytest tests/test_knowledge_corrections.py -q; expect missing-module failure first, then explicit behavior failures.
- [x] Implement pure input validation, source anchors, action composition, deterministic overlay and dependency-aware undo.
- [x] Run focused suite; expect all pass. Commit domain contract.

### Task 2: atomic service and common consumers

Create src/selfos/app/corrections.py and src/selfos/storage/corrections.py; modify storage/pipeline.py, storage/records.py, app/library.py, app/chat.py and model refinement contexts as needed. Test tests/test_correction_service.py.

Interfaces: load_corrections(vault: Path) -> dict; correct_knowledge(vault: Path, request: dict) -> dict. Under the canonical vault lock, recover pending journal, validate version and action request, atomically save .knowledge_corrections.json plus affected managed exports using commit(). Each mutation and undo returns action ID and backup ID. apply_corrections creates read/export contexts without changing generated state.

- [x] Write failing tests for repeated import/rebuild, fresh evidence conflict, stale version, partial write/recovery and undo preserving later generated evidence.
- [x] Implement allowed ledger path, validated loading, atomic mutation service and centralized read/export overlay.
- [x] Run focused/full pytest; expect pass. Commit service integration.

### Task 3: authenticated API and accessible UI

Modify web/routes/actions.py, app/library.py, web/scripts/knowledge-browser.js and en/zh-CN search catalogs; create separate correction UI module if browser script becomes unwieldy. Test tests/test_correction_routes.py and tests/browser/knowledge_corrections.py.

Interface: POST /__knowledge_correct__ accepts action, selected version IDs and editable fields or undo action ID. GET details includes compatible merge candidates and active action metadata. Reject cross-origin, unauthenticated, active import and stale/malformed requests before writing. Project merge remains project-alias capability; source-record merges enforce compatible category/relation/scope.

- [x] Write failing HTTP tests for protected mutation paths and integration results.
- [x] Add localized labelled edit form, explicit delete scope confirmation, compatible merge selector, correction badge/original evidence and dependency-aware undo list.
- [x] Run synthetic English/Chinese Chromium keyboard/edit/delete/merge/undo/source tests; expect no page errors or network/model calls.
- [x] Run full pytest and diff check; independent whole-branch review, fix important findings with RED/GREEN, publish PR after evidence passes.
