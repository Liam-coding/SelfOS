# Knowledge changes and conflicts (#17) — design for review

## Purpose

Show what a committed import or user correction changed, why it changed, and which sources support the old and new values. Keep current knowledge separate from historical snapshots and unresolved contradictions. Reuse the existing correction replay, temporal preferences, global browser/source navigation, backup manifests, and transaction recovery. No production imports or model calls are needed to build a change view.

## Current behavior verified in main a9d9875

- `.knowledge_pipeline.json` contains generated current records, historical records, source metadata, and project/session identity links. `record_version()` hashes category, value/text, scope, domain, and sources; it identifies a version, not a stable claim.
- `.knowledge_corrections.json` retains edit/delete/merge actions, original records, evidence anchors, dependencies, and undo state. `apply_corrections()` projects user intent over generated knowledge; later new evidence can create a correction conflict. It must remain authoritative.
- `merge_preferences()` uses sourced observations, explicit revisions, effective dates, and scopes. `history_records()` exposes prior preferences and project states. Ordinary chronology is already distinct from ambiguous contradictions.
- `storage.pipeline.commit()` backs up originals, journals a multi-file transaction, rolls back handled failures, and recovers unfinished writes. Backup restore checks after hashes and restores the affected files under a lock.
- Canonical publication occurs through `app.pipeline.install_rebuilt()`. Scratch extraction/refinement commits are resumable work and must not appear as committed knowledge changes. User corrections publish via `app.corrections.correct_knowledge()`. Run journals are best-effort observability and cannot prove publication.

## Alternatives

1. **Derive changes from backup manifests on every read.** Requires few new writes, but later snapshots and original/after hashes must be reconstructed. Cleaned or missing backups make past changes incomplete, and correction projection needs the correct historical ledger. This remains useful for a clearly labeled legacy fallback, not the new primary view.
2. **Store immutable change receipts with existing backups, publish a small head in the same knowledge transaction (recommended).** Receipts contain only affected record snapshots and operation metadata. Current records remain in the existing pipeline/ledger; the receipts are an audit view, never model context or editable competing knowledge. The transaction head makes publication verifiable and restore behavior explicit.
3. **Replace record storage with an event-sourced database.** Could offer a full revision graph, but would duplicate/rewrite current correction and preference semantics and require a much broader migration. Unnecessary for #17.

## Authoritative boundaries

- Current generated knowledge: pipeline state.
- Current user intent: correction ledger replayed over generated state.
- Current versus historical preference applicability: existing temporal projection at an explicit `as_of` instant.
- Past changes: immutable receipts, with snapshots clearly labeled as historical.
- Import execution/progress: existing operation journals and checkpoints; these do not count as published changes.
- Model context: receipt snapshots never enter model payloads. Preserve existing, privacy-filtered synthesis of `lesson_history` and `intent_history`; #17 does not remove those established context builders. Search/browsing retain the existing explicit current/history categories. Receipts are a separate historical audit view, not another search index.

## Identity and comparison

Do not change existing browser IDs or `record_version()` semantics. Add a pure comparison layer with three concepts:

- **Relation** groups claims: project ID for project cards; category + normalized key + normalized scope for facts/preferences. Project aliases resolve before comparison. Different scopes never silently overwrite each other.
- **Version** is an existing `record_version(category, record)`, plus a semantic snapshot fingerprint covering status, validity, conflict flags and meaningful project fields. This detects state changes that the browser version alone does not include.
- **Lineage** connects evidence anchors, existing history/supersession links, and correction action originals. Text-only lessons without an explicit connection are added/removed; similarity alone must not invent an update or merge. Multiple conflicting versions in one relation remain distinct.

Compare effective before/after views using the corresponding before/after correction ledgers, at one shared UTC `as_of` instant. Add optional `as_of` parameters to `apply_corrections()`, its `_entries()` helper, and `history_records()` and pass the same instant through every nested preference/history projection. Defaults preserve existing callers. Ignore storage/order bookkeeping and receipt metadata. Receipt classification is fixed at its recorded `as_of`; merely reaching a future effective date changes the live applicability label, not a stored event. A later committed operation can record that now-effective transition.

Pairing is deterministic and conservative, in this order:

1. Exact semantic snapshot fingerprints cancel unchanged records one-to-one. Repeated copies are treated as a multiset, not erased by a dictionary key.
2. Explicit correction edit/merge/undo maps versions from ledger originals to the resulting manual record. A merge is one event with multiple before snapshots; undo uses its action dependencies.
3. Accepted preference supersession/revision links map old values to replacements in the identical normalized relation tuple `(category, normalized(key), scope_type, resolved_scope)`. Facts use the same relation tuple, but dates alone never establish a replacement.
4. A unique identical claim payload (category/value/text/scope/project/status/validity) with only different support is `updated: support_added` or `support_changed`, even if source IDs are entirely replaced. This is claim equality, not fuzzy similarity.
5. For remaining versions, shared direct source/evidence anchors establish lineage only if there is exactly one unmatched predecessor and successor in that relation. Content and evidence can change together under that unique link.
6. Ambiguous one-to-many/many-to-one or entirely replaced content+evidence falls back to separate additions/removals with an unresolved matching reason; never guess an update. Text-only lessons require explicit correction or source/evidence lineage.

Primary counts count events, while each event separately reports affected before/after version counts. Conflicts are an independent count/flag, so a conflicted addition is not counted as two primary changes.

## Change classifications

Use a primary action plus independent conflict/applicability metadata:

- `added`: a newly retained claim.
- `updated`: same explicitly linked claim/lineage with changed content or supporting evidence.
- `superseded`: a current claim moves to history with an explicit replacement or temporal transition, retaining the replacement link and effective date.
- `invalidated`: explicit evidence or an existing validity/status rule says the claim is no longer applicable. Require the reason; absence from a rebuild alone does not prove falsity.
- `removed`: absent from the effective current view without an explicit invalidation, including a user deletion, scope exclusion, or changed retention policy. Keep the cause distinct.
- `merged` / `restored`: explicit user merge or undo, with originals and action dependencies retained.

An unresolved contradiction is a `conflict` flag with a reason and competing version/source references, not a primary temporal action. Newer dates do not automatically win for facts. Explicit preference revisions resolve only matching value/key/scope and supported time semantics already accepted by preference logic. Manual corrections remain preferred current intent; later conflicting evidence is shown for review rather than overwriting or resurrecting suppressed lineage. No additional LLM adjudication is introduced. Existing edit/delete/merge/undo controls can resolve conflicts by recording user intent.

## Transactional storage

Add a small allowlisted `.knowledge_change_head.json` containing schema version, `audit_tip` (latest committed event reference/hash), `state_tip` (event defining current knowledge state), and current canonical/ledger hashes. Every receipt has an `audit_parent`, preserving the complete event sequence even after restore. The head does not grow with the lifetime number of operations. Add `change-receipt.json` next to the existing canonical transaction's `pipeline-manifest.json`, under `.knowledge_backups/<run_id>/<index>/`. Each receipt includes operation identity/kind, UTC recorded time, optional effective dates, before/after canonical and ledger hashes, affected snapshot part references, action reasons, and provenance metadata. Do not copy full conversations.

Every receipt also records `state_before_tip` and `state_after_tip`. For ordinary import/correction/undo, the former is the current head's state tip and the latter is the new event reference. For restore, the former is the current state tip and the latter is the target operation's verified `state_before_tip`. Audit ancestry and state ancestry are deliberately different after reversal.

The receipt is prepared before publication, but it is not visible as committed solely because its file exists. Publish its reference/hash in the same `commit()` write set as canonical state and/or the correction ledger and managed Markdown. The existing pending journal also covers the head. A failed transaction rolls the head back; unreferenced prepared receipts are hidden. Interrupted writes recover under the existing lock before any reader validates the chain. Readers must reject tampered hashes and malformed/oversized metadata.

Hooks are explicit at canonical `install_rebuilt()` and `correct_knowledge()`, after current privacy/settings/hash checks and correction projection under the same lock. Do not hook every scratch `commit()`. User undo captures an operation with action ID and before/after ledger states. A no-change publication can have a receipt with zero changes; it must not fabricate additions or count checkpoints as operations. Retries reuse operation identity and identical fingerprints, rejecting different content under one identity.

### Restore and recovery

Restore is a new transaction with a new immutable **restore receipt**, not literal restoration of the old audit head. Its `audit_parent` is the pre-restore audit tip, its `state_parent` is the restored state's prior head reference from the validated backup originals, and `reverted_receipts` names the exact operations being reversed. The new head's audit tip points to this restore event and its state tip points to the restored state. Canonical/ledger/managed files and the new head are in the same pending journal/write set. Both canonical restore entry points must use this shared helper.

Validate after hashes of knowledge files as today; treat the audit head as a monotonic control record, not a knowledge file to blindly reverse. Verify current head, the target receipt, backup before-state hashes, and restore dependency/state ancestry before computing inverse writes. Reject already-reverted or unrelated targets. A subsequent import links its audit parent to the restore receipt and compares against restored current state. A failed restore rolls back the new head and files together. A crash after journal removal still leaves a valid restore receipt referenced by the head. Existing `restored`/`rolled-back` markers remain auxiliary UI/legacy information, never the proof of receipt publication or reversion.

Immutable receipt files stay beside their backup manifests. The audit chain retains both the original operation and the restore event; UI marks the former reverted using verified restore references. Unreferenced prepared receipts are hidden. Migration exports the audit chain including restore events and treats any deliberately omitted ancestor as an explicit historical boundary.

First release forbids backup restore of a restore transaction and rejects restoring an already-reverted target. It does not automatically reactivate earlier reverted operations. Existing user-action undo is an ordinary committed correction event, not backup restore-of-restore. Example: A → B → restore B leaves state A and audit tip restore-B; C then has state-before A and audit-parent restore-B. Restoring C is allowed and returns A; restoring B again or restoring restore-B is rejected.

Restoration remains all-or-nothing under the knowledge lock. Validate the receipt/head linkage before showing details. Test interruption at receipt preparation, head publication, canonical write, and restoration. Do not claim protection against sudden power loss beyond the existing filesystem durability guarantees.

## Bounded reads and migration

Receipt files and head reads have explicit byte limits and contained paths; directory discovery and UI paging are bounded. Selected partitioning: pack deterministic change entries and deduplicated source metadata into `changes-000001.json` parts, at most 4 MiB each and 64 MiB of decoded audit payload per operation; the root receipt is at most 1 MiB and the head at most 64 KiB. Publish all part hashes together through the root/head. A single entry exceeding the part cap or operation exceeding the total cap fails before canonical publication with an explicit recoverable error; actual events are never silently truncated. These are audit payload limits, not a target number of retained knowledge items. Existing knowledge remains intact on rejection.

Legacy vaults without a head keep working. The first new operation starts an audit chain from the current effective state; it does not pretend to know earlier import changes. Existing historical records remain browsable. A legacy backup-derived view, if supplied, is labeled inferred/incomplete and is not required to fabricate receipts.

Portable migration uses package version 2 when carrying audit history and continues accepting version 1 as legacy baseline state. The existing 64 MiB total decoded package limit remains. Audit export is an explicit separate choice: `none`, a recent whole-operation range, or `all`. Before export, display the included operation range, bytes and whether earlier history is omitted. Full backups remain an independent opt-in.

For a recent range, export the current head and complete root/parts for contiguous audit ancestors that fit the selected range and total byte budget. Store an audit manifest with included root hashes and the exact omitted ancestor boundary; never cut an event/part or silently drop operations to fit. If even one chosen operation cannot fit beside canonical data, fail before download and offer no-history export or a smaller range; do not increase the limit silently. An all-history export over the cap fails with an explicit limit message. Multi-volume audit archives are deferred; #17 guarantees explicit bounded partial-history migration, not arbitrary-size full export.

On import, validate every included root/part and chain link before writes. Only a declared omitted boundary may be absent. Historical details and reverted-target links beyond that boundary show **history not included in this export**. No-history imports start a documented baseline with no audit tip; they do not reconstruct or claim past events. Keep an `audit_import_boundary` in migration metadata for incomplete history. Preserve unresolved source metadata and privacy exclusions; credentials and raw harness conversations remain excluded.

## UI and shared import-center interface

Add a **Knowledge changes** entry in the existing knowledge area. An operation list shows recorded time, operation type, counts, and applied/reverted status. Selecting an operation shows categorized changes with before/after values, explanation, effective dates, and source links. Filters cover category, primary action, and unresolved conflict. English is default with Chinese catalogs. Loading/empty/missing-history/invalid-metadata states are explicit and accessible; no raw schema fields are exposed to users.

Existing knowledge detail keeps current values prominent and links to historical change detail. Historical versions link receipt/event IDs, not nonexistent current browser IDs. Add a history source lookup scoped by receipt/root/part hash and source ID: validate the published receipt chain first, read its stored source metadata, then reuse current root selection/privacy exclusion and original-message identity/content verification. Never add old metadata back into canonical sources merely to view history. Missing, changed, denied or migration-omitted sources have distinct localized states. Resolving a conflict uses existing correction controls and creates a new receipt; it never edits a historical receipt.

Provide an authenticated operations/changes API that never changes canonical knowledge. Operation-list cursors carry the initial head revision, next audit ancestor reference/hash, category/action/conflict filter fingerprint, and accumulated reversion state when traversing restore events. Per request inspect at most 100 roots, 32 receipt parts, and 16 MiB of bytes; detail cursors carry root/part/entry position. Empty filtered pages still return a continuation cursor if scanning remains. Never scan the entire lifetime to calculate a total: return `total: null`, `scanned`, and `has_more` unless a verified chain end is reached within the bound. Invalid cursors are rejected; a changed head returns `reset_required` and a fresh first-page cursor.

Opaque cursor IDs reference disposable cache metadata, never receipt or knowledge records. Scope the cache to the authenticated session and head revision; expire after 15 minutes and bound active cursors/storage. Reversion context is partitioned into 4 MiB cache parts with a 64 MiB cursor-context cap, carrying exact IDs from verified restore events. If this bound is exceeded, return an explicit `history_navigation_limit` with a direct operation lookup fallback; never label uncertain operation status as applied. Cache expiration returns a restart-required response. Caches are excluded from migration and may be deleted without losing history. The list remains a paged exploration, not an unlimited global historical search feature.

Direct operation/history-source detail requires a publication proof stored in the authenticated cursor cache, bound to the current head revision and the exact verified root/part hashes. Paged traversal creates these proofs only for roots reached through the trusted audit tip. A deep link without proof starts bounded ancestor verification (same per-request root/byte limits), returns `verification_pending` plus continuation, and exposes no historical snapshot as committed until membership is established. If the chain ends or the migration boundary is reached without membership, report missing/not-included; exceeding navigation limits reports unverifiable history rather than bypassing proof. Head changes invalidate proofs and require verification again. The direct-lookup fallback does not promise unbounded or proof-free access.

The future import center (#16) links committed jobs to receipt IDs; stopped/failed jobs link only to their checkpoints and diagnostics. The source of operation counts is shared, not reconstructed independently by each page.

## Five examples

1. **Changed preference:** global editor preference VS Code, then an explicit sourced switch to Zed effective next month. Until that date VS Code is current and Zed is scheduled; afterward the former value is historical and linked as superseded. Contradiction is not inferred from this transition.
2. **Contradictory fact:** two supported current facts give different graduation years with no accepted resolution. Both remain traceable in one scoped relation; UI shows unresolved conflict, not an invented latest winner.
3. **New support:** a second source confirms the same recovery preference. One claim remains; the receipt reports added evidence and links both sources.
4. **Manual correction:** user changes a inferred project goal. Generated state and correction originals remain intact, current projection follows the user. A later conflicting model proposal is shown as a conflict and does not overwrite the correction.
5. **Deleted record:** user deletes a lesson. Its evidence lineage is suppressed in future replay; the receipt preserves the historical before-value and action. Undo creates a restored operation. Backup restore marks reverted operations and returns current state/head consistently.

## Acceptance evidence before completion

- Unit fixtures for all five examples, scope differences, aliases, invalidation versus removal, deterministic comparison, and unknown dates.
- Canonical import/correction/undo transaction tests; scratch work produces no committed receipt.
- Rollback/interruption/restore, tampered receipts, oversized/partitioned records, pagination/revision consistency.
- Portable migration with and without full backups; invalid receipts rejected before writes; source/privacy behavior retained.
- Browser tests for English/Chinese, mobile layout, before/after values, conflict editing, historical/source links, applied/reverted operations and empty/error states.
- Current search/model context excludes receipt snapshots; frozen acceptance fixtures remain unchanged.
- Small isolated fixtures and loopback providers only.

Status: proposed design awaiting review. Product implementation has not started.
