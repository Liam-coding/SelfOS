# Knowledge Changes Implementation Plan

> Execute inline with superpowers:executing-plans; one fresh whole-branch review at the end. The already approved #17 design is binding.

**Goal:** Show traceable committed knowledge changes and unresolved conflicts without treating checkpoints or history snapshots as current knowledge.
**Architecture:** Pure effective-state comparison feeds immutable partitioned backup receipts. A small head publishes their hashes atomically with the existing canonical transaction. Authenticated bounded navigation validates ancestry before exposing historical snapshots.
**Tech Stack:** Python standard library, existing transaction/correction/preference logic, packaged JS/locales, pytest and synthetic Chromium.
**Spec:** docs/superpowers/specs/2026-11-13-knowledge-changes-design.md from feat/knowledge-changes (PR67, approved implementation scope).

## Global Constraints
- Source and frozen acceptance fixtures unchanged; no paid model, personal vault, upstream execution or physical Mac claims.
- Receipts are audit only: no extraction/model-context/search index changes. Current correction replay and temporal preference rules remain authoritative.
- One explicit shared UTC as_of for before/after projection; default existing callers preserved.
- Head64KiB, root1MiB, parts4MiB each, decoded audit64MiB/operation; reject rather than truncate.
- Navigation/request100 roots,32 parts,16MiB; total:null until bounded verified end; changed head resets navigation.
- Session-bound opaque cursor cache15min, context parts4MiB,total64MiB; bounded cache count/storage; no secrets/cursors in migration.
- Migration v2 for audit, accepts legacy v1; total decoded package64MiB. none/recent/all audit choices; complete operations only; explicit omitted boundary.
- Restore creates a new audit event; audit and state tips diverge. Reject restore-of-restore and already-reverted/unrelated targets.

## Rulings required by concrete encoding
- Root state_after_tip for its own new state uses the event identity (run_id,index), not its own root hash, avoiding a self-referential hash. The atomic head carries the complete identity/hash reference; readers verify matching identity. Existing prior state references carry verified hashes. Cost if wrong: versioned receipt format migration; no loss of canonical knowledge.

## Review Focus
- A preference becomes effective between comparison passes: both projections use one explicit instant (Task1).
- Existing duplicate record versions are not erased by dict identity; comparison is a multiset (Task1).
- Receipt preparation survives a crash but the head does not: unreferenced records stay invisible (Task2).
- Restore follows a later import: audit ancestry and current-state ancestry are validated separately (Task3).
- Recent migration omits the target of a retained restore event: status is not-included, never invented applied/reverted proof (Tasks4/5).

## Task1: Effective comparison and fixed-time replay
Files: knowledge/changes.py, knowledge/corrections.py, knowledge/history.py; tests/test_knowledge_changes.py.
Interfaces: compare_changes(before,after,before_ledger,after_ledger,*,as_of,operation,action_id=None)->list[change]. apply_corrections(state,ledger,*,as_of=None); _entries(state,*,as_of=None); history_records(state,*,as_of=None).
- [x] RED: five design examples; different scopes; alias resolution; multiset duplicates; project status/support changes; ambiguous lineage yields additions/removals; facts are not replaced by dates; future applicability uses one instant; removal does not imply invalidation; explicit user merge/undo one event.
- [x] Implement deterministic semantic snapshots, existing versions, relation/lineage pairing in design order; preserve before/after source references and independent conflict flags. Ignore storage bookkeeping.
- [x] Run comparison/preference/history/correction/architecture tests; expect green. Commit.

## Task2: Immutable bounded receipt storage and canonical publication hooks
Files: storage/change_receipts.py, app/change_publication.py, storage/pipeline.py, app/pipeline.py, app/corrections.py; tests/test_change_publication.py.
Interfaces: prepare_receipt(vault,*,run_id,index,kind,before_state,after_state,before_ledger,after_ledger,before_hashes,after_hashes,as_of,action_id=None)->head bytes; read_head(vault)->dict; read_root(vault,ref)->dict; read_part(vault,ref,number)->dict. publish_changes(vault,writes,run_id,index,*,kind,action_id=None)->None invokes existing commit with head included.
- [x] RED: only canonical install/correction/undo produce receipts; no scratch receipts; published tip hash verifies; exact retry identity accepted/different retry rejected; zero-change event count0; parts deterministic/deduplicate metadata; caps fail before canonical writes; tampered paths/hashes rejected.
- [x] Prepare immutable root/parts beside manifest using contained IDs; atomically add head to existing write set. Capture corresponding canonical state/ledger hashes under the same lock. First event baselines legacy current state.
- [x] RED/GREEN interruption at prepare/head/canonical write/journal removal; rollback hides unreferenced receipt; readers recover before chain checks.
- [x] Run publication/corrections/pipeline/current-import/architecture tests; commit.

## Task3: Restore receipts and state ancestry
Files: storage/change_restore.py, storage/pipeline.py, app/knowledge.py; tests/test_change_restore.py.
Interfaces: restore_changes(vault,run_id)->restore operation result, called by both canonical restore entrypoints; validates current audit/state head and target receipt before inverse writes.
- [x] RED: A,B,restoreB,C,restoreC state A and monotonic audit chain; reject second restoreB/restore-of-restore/unrelated target; changed after hash fails; restore rollback/pending recovery atomic; markers do not establish publication.
- [x] Reuse existing validated backup inverses excluding historical head as ordinary knowledge; publish new restore root/head/files in one existing commit. Verify exact reverted refs and prior state tip. Legacy baseline restores remain explicitly legacy, never fabricate old receipts.
- [x] Run restore/publication/pipeline/checkpoint tests; commit.

## Task4: Bounded authenticated navigation and historical sources
Files: storage/change_cursors.py, app/changes.py, web/routes/dashboard.py; tests/test_change_navigation.py and tests/test_change_http.py.
Interfaces: list_changes(vault,*,session,cursor=None,category='all',action='all',conflict=False)->page; change_detail(vault,event_id,*,session,cursor=None)->page; change_source(vault,event_id,source_id,*,session,proof,offset=0,limit=24000)->source page.
Routes: authenticated GET /__knowledge_changes__, /__knowledge_change__, /__knowledge_change_source__; auth session identity is obtained from the existing authenticated request boundary, never trusted query input. Cursor count128 maximum and64MiB aggregate cache storage; expired entries may be removed.
- [x] RED: session isolation/expiry/cache caps; head reset; cursor/filter tamper;100 roots/32parts/16MiB bounded traversal; filtered empty continuation; reversion context after restores; deep link returns verification_pending until ancestry proof; omitted/missing/tampered states distinct.
- [x] Implement contained expiring opaque cursor cache bound to session+head+filters, exact proof refs from trusted ancestry only. No unbounded totals or proof-free direct lookup.
- [x] RED/GREEN historical source viewing freshly verifies current privacy/original bytes without reinserting old metadata; denied/changed/migration-omitted sources distinct. API local/auth guards and no writes to canonical knowledge.
- [x] Run navigation/HTTP/privacy/source/library tests; commit.

## Task5: Explicit portable audit ranges
Files: app/change_migration.py, app/migration.py, app/privacy.py, web/routes/actions.py, scripts/privacy.js, locales; tests/test_change_migration.py.
Interfaces: audit_export(vault,*,mode='none',recent=20)->{files,manifest,summary}; validate_audit_import(decoded,manifest)->boundary; existing export_package(...,audit='none',audit_recent=20) accepts explicit choice.
- [x] RED: legacy v1/no-history baseline; v2 recent/all contiguous complete operations; declared omission only; omitted reversion target distinct; tampered/missing parts reject before writes; audit64MiB package bound; no credentials/raw native files/cursor caches; no silent range clipping.
- [x] Preserve independent full-backup option, source rebasing/unresolved native paths/privacy rules and audit_import_boundary. UI preview names selected range/bytes/boundary before download.
- [x] Run audit migration/current migration/uploads/privacy tests; commit.

## Task6: Localized operations and before/after UI
Files: web/templates/changes.html, web/scripts/changes.js, web/styles/changes.css, web/scripts/knowledge-browser.js, manifest, locales/en/changes.json, locales/zh-CN/changes.json; tests/test_change_browser.py and tests/browser/changes.py; both READMEs.
- [x] RED: entry button, list counts/event filters, before/after historical detail, sources, current correction navigation, conflict flags, applied/reverted state, empty/loading/invalid/not-included/navigation-limit states.
- [x] Render through safe text nodes and existing design tokens, English default; explicit paged load more/reset; preserve current values outside audit dialog; no import/model action on opening.
- [x] Real authenticated synthetic Chromium en desktop light/zh mobile dark: import, user edit/delete/merge/undo, backup restore; inspect before/after/source links and stale head reset; no model/private calls.
- [x] Run focused and full suite, installed package checks, fresh whole-branch review; Important/Critical RED/GREEN then final full suite. Create English implementation PR linked #17 only after all requirements pass.

Self-review: each approved design section has a task; exact interfaces above are consistent. Archive receipts are not an additional model/search input. Cursors remain disposable/session-scoped, and recent migration only omits a declared whole-operation boundary. Implementation is already authorized by the user's continuing instruction; execute inline without another approval loop.

## Final implementation evidence

- Full regression after the single whole-branch review fix pass: 1370 passed, 6 skipped in 535.11 seconds.
- Real authenticated Chromium: English desktop/light and Chinese mobile/dark, import/edit/delete/undo/merge/restore, source viewing, safe text, head reset, conflict filtering, project field differences and current-record history lookup.
- Independent wheel: publication, verified detail, backup restore, catalogs and packaged web assets passed.
- Frozen acceptance fixtures were not changed; no paid model or personal-vault import was performed.
- Important review findings (no-history/full-backup restore, cache exhaustion, hidden project changes) reproduced with RED/GREEN regressions and fixed. The same pass implemented concrete export ranges, restore-target links and record-history lookup. No review findings remain deferred.

## Recorded implementation rulings

1. New state references use the event identity in their own receipt; the head binds its hash. This avoids a self-referential hash. A later encoding change needs a versioned audit migration, without losing canonical knowledge.
2. Canonical/head mismatches remain errors. Tests emulate new generated evidence through the real publication boundary. Direct external edits require an explicit baseline repair, rather than silently inventing audit continuity.
3. Migration preserves immutable receipt bytes and original hashes, while rebasing the current canonical hashes. Historical full-backup restoration remains conservative when imported paths or bytes differ.
