# First-run onboarding implementation plan

Use superpowers:executing-plans inline, TDD, and one independent whole-branch review at the end. User already authorized sequential execution. Spec: docs/superpowers/specs/2026-11-13-first-run-onboarding-design.md.

**Goal:** #24 recoverable first useful result without an accidental whole-history import.

**Architecture:** source settings and bounded previews are separate from canonical knowledge; a persisted transport budget and scoped sample pipeline reuse existing CLI/SSE/checkpoints/publication. Packaged UI/i18n uses the existing settings/browser/progress components.

## Review focus

- Read/skip/resume/preview never calls the model or modifies existing knowledge/model settings.
- Limits apply before content reads; symlinks, oversize files and changed previews cannot widen processing.
- Cached context respects exclusions; unrelated knowledge survives old-schema sample publication.
- The same budget counts all HTTP attempts across stops/resumes; partial session identity does not conceal unprocessed content.
- Custom-root source links work; browser language changes preserve input and do not duplicate requests/tasks.

### Task 1: source selection, bounded previews and cumulative budget

Create src/selfos/sources/selection.py (validated roots/exclusions and bounded file/message selection), src/selfos/storage/onboarding.py (contained JSON/progress/preview/budget persistence), src/selfos/app/onboarding.py (orchestration/status). Test tests/test_onboarding_sources.py and tests/test_onboarding_budget.py.

Interfaces: load_sources(vault, defaults=None) -> dict(version=1, roots:list[str], exclusions:list[str]); save_sources(vault, value) -> dict; discover_sources(defaults=None) -> list[path/available/source]; allowed_source(path, selection) -> bool. Paths/exclusions are absolute file/directory prefixes; roots maximum20, exclusions maximum100, JSON maximum64KiB. Missing saved roots remain visible as unavailable; new custom roots must be real directories. Exclusions are contained within selected roots. No registry implies existing defaults.

build_preview(vault, tier='sample') -> dict with UUID id, counts, messages/excerpts to display, file/project identities, clipping/warnings and budget12. Enumerate at most2000 entries, select at most2 newest eligible JSONL files (8MiB each), at most20 messages per session, at most2 compact parts. Store file hash/size/mtime, selected message IDs and compact-part fingerprints; regenerate/revalidate only recorded files on resolve_preview(vault,id), reject changed source/policy/config. Records keep original IDs/paths; no fake source copies. Preview JSON contains bounded source material and stays local. Explicit tier='more' uses4files/4parts/40messages/24requests; no unbounded tier or automatic expansion.

SampleBudget(vault, preview_id).claim() persists used+1 under a separate lock before an HTTP attempt; status() returns used/remaining/limit12. Reload/resume share the same preview budget; invalid files fail closed. Only create_preview/new_allowance explicit action creates a new UUID/budget after revalidation. ModelBudgetExceeded has an actionable safe message.

- [ ] Write and observe failing tests for source validation/exclusions, metadata-only discovery,2file/20message/2part limits, hash/policy changes, oversize/symlink skip and no source-byte changes.
- [ ] Implement selection and contained versioned storage with atomic writes.
- [ ] RED/GREEN budget tests: two instances/process-safe claims share remaining quota; exhaustion and failed requests consume attempts; corruption rejects and resume cannot reset.
- [ ] Run focused tests and commit.

### Task 2: real transport and scoped pipeline integration

Modify providers/client.py request_opener(root, budget=None), providers/knowledge.py api_summarizer/api_refiner keyword budget; all internal reviews reuse the wrapped opener. Test tests/test_onboarding_pipeline.py and transport tests.

Modify app/knowledge.py run_knowledge(..., selected_messages=None, selected_sessions=None, sample_id=None), app/pipeline.py consolidate_sessions(..., upgrade_history=True), refine_projects(..., project_ids=None, context_filter=None, upgrade_history=True), install_rebuilt(..., selected_projects=None). Existing defaults/signatures remain compatible.

Sample supplies validated preview sessions, adds a partial-input fingerprint marker, forces incremental scratch initialized from current canonical state, skips unrelated global history upgrades and refines only touched projects. Preserve old global schema/policy/quality fields on publication when they predate the sample; mark sample coverage separately rather than claiming a whole-vault upgrade. Selected-project install checks/exports preserve unrelated cards even if their legacy detail exceeds current sample policy. Existing backup/journal/corrections machinery remains authoritative.

Context filtering rebuilds model-safe project context from saved summaries with only allowed classified sources. Omit mixed/unknown support, filtered lessons, intent history and correction provenance from requests; do not delete local history. Persist source selection for future default imports. Include safe manual correction intent in the actual provider prompt (current payload-only correction metadata is not yet serialized). Filter before fingerprint/model validation; empty safe project context skips model refinement. Custom registered roots authorize source viewing without allowing arbitrary file access.

- [ ] RED/GREEN tests: old-schema unrelated card/lessons preserved; no model call for unrelated projects; partial sample vs later complete-session fingerprint differs; excluded cache text absent from captured HTTP payloads; safe manual intent reaches prompt.
- [ ] RED/GREEN transport tests: extraction/refinement/reviews/retries all share persisted12claims, exhaustion preserves checkpoints; no reset after stop/resume.
- [ ] Implement CLI --onboarding-preview UUID, source selection and wrappers; resume revalidates preview, keeps same budget. Existing ordinary CLI uses configured roots/exclusions or prior defaults.
- [ ] Run focused pipeline/architecture/source-view tests and commit.

### Task 3: authenticated API and localized recoverable guide

Modify web/routes/actions.py and dashboard.py; create web/rendering/onboarding.py and packaged web templates/styles/scripts/onboarding.* plus en/zh-CN/onboarding.json; extend manifest and dashboard refresh. Use storage/onboarding contained paths, existing local/auth gates and body-size limit. Test tests/test_auth_onboarding_routes.py and tests/test_onboarding_service.py.

GET /__onboarding__ returns progress, availability, public model status and published counts. POST actions save_sources/save_step/skip/resume/preview/new_allowance/start validate input; start returns the existing stream URL with a validated preview ID, not text/paths. Stream handler passes --onboarding-preview to the existing child and never falls back to default discovery on invalid preview. Block settings/preview mutation during an active import. Starting a sample requires an explicit button; all default rendering/status calls are read-only.

Fresh profile Get started CTA, Settings Resume setup entry, closable five-stage dialog. Reuse model/network settings with an explicit one-request test label, source/custom directory and exclusion inputs, local preview counts/excerpts/budget, sample start/stop/resume/provisional/published results and source browser. New budget label explicitly says it grants another12requests. Skip/resume persist state; language changes keep values/focus. Empty sources, file limits, stale preview, exhausted allowance and connection failures have catalog keys and recovery controls. Existing profile never auto-opens or replaces settings/knowledge.

- [ ] RED/GREEN protected API tests and service tests for no model side effects on read/skip/resume/preview, corrupted progress, stale IDs and concurrent task rejection.
- [ ] Implement UI/resources/i18n; run existing frontend architecture and locale tests.
- [ ] Real Chromium fixture: fresh and existing profiles, custom roots and exclusions, failed/successful model test, preview without modelcalls, sample result/source access, stop/reload/resume, skip/reopen and English/Chinese unsaved inputs.
- [ ] Run focused tests and commit.

### Task 4: final validation, documentation and PR

Create docs/first-run-onboarding.md; link README English/Chinese and settings/import guides. Browser test under tests/browser/onboarding.py uses synthetic directories and loopback model, never production discovery or paid calls. Reuse integrated browser setup where useful without adding production hooks.

- [ ] Full pytest and installed-wheel foreign-cwd onboarding check; assert source/credential/initial-state bytes preserved until explicit authorized operations.
- [ ] Requirement audit and one fresh whole-branch reviewer; fix Important through RED/GREEN and repeat affected checks.
- [ ] Record actual tested commit, budget/profile evidence and platform limits; diff/frozen checks.
- [ ] English PR Closes#24 only when requirements pass; CI then merge. #38 real-model evaluation remains separately pending user authorization.
