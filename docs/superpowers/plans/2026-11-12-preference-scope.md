# Preference scope and revision implementation plan

> For agentic workers: use superpowers:executing-plans inline, with failing tests before product code and independent read-only review before merge.

**Goal:** Implement #40 end to end: sourced preferences retain independent applicability, historical revisions and unresolved contradictions.

**Architecture:** A focused knowledge/preferences.py module validates applicability metadata and merges preference groups by normalized relation plus scope. Existing validation, extraction, checkpoint persistence and library rendering compose that domain logic. Keep the current Python/JSON/Markdown/browser stack and shared localization runtime.

**Spec:** https://github.com/Liam-coding/SelfOS/issues/40 and docs/preferences-investigation.md. Base: main e4f532e after PR #50 passed all four macOS CI jobs and merged.

## Design decisions

- New extraction scope is an object with type global/activity/project/unknown and an id. Global and unknown require an empty id; activity requires a stable descriptive id; project requires the current session project identity. Stored records retain a string scope plus scope_type for compatibility with existing readers and evaluation cases.
- Missing legacy scope becomes unknown, never an asserted global preference. An explicitly stored legacy global string remains global; other explicit legacy string scopes remain declared activity contexts. Keep unrelated scope groups independent.
- Scope identity includes type and id. Legacy declared activity ids are case-folded without removing punctuation; project ids remain opaque. Conflicting scope/type metadata is rejected.
- Each supporting_observations entry contains one actual quoted source id, exact quotation and original source timestamp; contextual source ids remain traceable but never change preference chronology.
- Equality uses relation, scope and normalized value. Equivalent statements union source support, exact quotations and observation dates. Do not upgrade attribution or broaden scope.
- Only unambiguously later timezone-qualified source observations may supersede a differing current value. Equal or incomparable dates keep both current values with conflict metadata and source-linked alternatives. Dates must be compared as instants, not lexicographically; ambiguous dates must never silently win.
- A later matching value recomputes the entire conflict group. Undated support remains incomparable. A -> B -> A keeps old A and current A as separate sourced stages; retrying the latest input is idempotent.
- Preserve displaced records in records_history with original_category preferences and temporal historical. Record source-linked supersession. Expose valid_until only for an explicit sourced revision; observation-based supersession alone is not proof of an exact end to the old preference.
- Explicit revision is a boolean supported by the same source quotation, never a model-supplied clock or unsupported predecessor ID. Source validation and conservative retention remain intact. Existing user-authored Markdown outside managed sections stays unchanged. Durable correction integration must preserve existing correction metadata rather than overwrite it.
- Display applicability, conflicts and supersession in knowledge details and managed Markdown, with keyed English/Chinese labels and literal user data. Search identities include applicability so distinct contexts cannot collide.
- Preserve existing storage formats, cancellation/checkpoint/backup guarantees, private source bytes and frozen acceptance files. Test using synthetic sources only, no production import or model calls.

## Review focus

- Different scopes, same key/value; unknown legacy versus explicit global.
- Equal timestamps, timezone offsets, date-only/missing/invalid dates and older arrival.
- A later matching value resolves a prior tied conflict; repeated evidence never loses source support.
- Explicit change cycles and historical copies preserve source references and avoid stale active instructions.
- Strict schema, old saved records and interruption/resume all use the same scope semantics.

## Task 1: Domain scope and chronology

Files: knowledge/preferences.py, knowledge/records.py, tests/test_preference_scope.py, evals/preference_holdout.json (read only).

- [x] Add failing independent-scope, tied-contradiction, unknown-scope, timezone/date ambiguity, repeated-conflict resolution and historical source-link tests.
- [x] Implement normalize_scope(record, session=None) and merge_preferences(state, record), composed by validate_record/merge_records. Keep all five supplied-candidate sequence cases passing without changing their expected labels.
- [x] Verify focused domain/policy/holdout tests (52 passed) and pipeline/source regressions (109 passed), then commit the tested deliverable.

## Task 2: Extraction contract and source-backed revisions

Files: knowledge/evidence.py, providers/knowledge.py, providers/reviews/scope.py, tests/test_knowledge_evidence_protocol.py, new protocol tests.

- [ ] Add failing schema/resolution tests for typed scope, invalid ids, old responses, explicit revisions and current-project mapping.
- [ ] Extend strict record schema and prompt instructions together. Resolve project aliases locally; carry applicability through retention review without losing it or reclassifying a recurring contextual preference as a temporary project request.
- [ ] Add independently labeled synthetic source-session holdout (separate from supplied-candidate merge scores). Use it to pin extraction contracts, and explicitly report that no end-to-end model-quality evaluation was performed.
- [ ] Verify schema/provider/validation regressions and commit.

## Task 3: Storage, library and release

Files: storage/records.py, app/library.py, resources/web/scripts/knowledge-browser.js, locales/*/search.json, preference persistence/UI tests and docs/preferences-investigation.md.

- [ ] Add failing persistence/search-detail/JS tests for scope identity, source-backed historical revisions and localized conflict/applicability labels.
- [ ] Render scope and conflicts without changing literal sources; preserve manual notes, backup/resume behavior and all existing library routes.
- [ ] Verify all five holdout sequences, full suite, actual synthetic browser, packaged wheel/frozen5 and independent review.
- [ ] Create an English PR against main with Closes #40 only when all requirements pass; merge after live CI succeeds under the user's existing authorization.
