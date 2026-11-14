# Document Upload Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task.

**Goal:** Deliver #11 from authenticated local upload to selected organization and original-source navigation.
**Architecture:** Dedicated upload admission/registry recovery owns immutable originals; document adapters normalize redacted evidence; existing knowledge jobs own model work and canonical publication.
**Tech Stack:** Python 3.10+, standard-library HTTP/filesystem/JSON, existing pytest and packaged classic browser scripts.
**Spec:** `docs/superpowers/specs/2026-11-13-document-upload-design.md` (approved by user).

## Global Constraints
- UTF-8 TXT/Markdown, 20 MiB per original; at most 10 sequential UI uploads.
- Upload/preview perform no model calls or local conversation scans. AI documents are quoted_dialogue.
- Preserve originals, corrections, source validation, privacy, selected coverage, stop/resume and backups.
- Registry limit 2,000 originals, total original/quarantine storage 512 MiB; transfers capped at 30 seconds, 64 KiB reads.
- Existing isolated worktree only; synthetic runtime/fixtures only; no private vault or paid models.
- Documentation PRs remain separate from implementation; related issues remain open until full acceptance.

## Review Focus
- Concurrent duplicate uploads publish one original and never reset its processing state (Task 1).
- Disconnect after admission publication can be retried without creating another identity (Tasks 1/2).
- Cross-fragment credentials are redacted before slicing and remain unexposed in source navigation (Task 3).
- Restore after processing cannot leave a false completed upload (Task 4).
- Upload cancellation/auth expiry/locale change preserves completed local admissions and never starts a model (Task 5).

## Task 1: Recoverable admission and registry
**Files:** Create `src/selfos/storage/uploads.py`, `src/selfos/sources/upload_admission.py`; tests `tests/test_upload_admission.py`.
**Interfaces:** `admit_document(vault, filename, stream, length, *, cancel=lambda:False) -> dict`; `list_documents(vault, offset=0, limit=50) -> dict`; `recover_uploads(vault) -> None`. Result has `document` and `duplicate`; entries have id/profile/hash/path/name/size/uploaded_at/provenance.
- [ ] Add tests: exact BOM bytes preserved, duplicate txt/md reuses id/time, rejected filename/format/length/UTF-8/EOF/cancel has no ready entry, outside symlink denied, registry corruption not reset, publication failures recover, concurrent duplicate and changed-original quarantine repair preserve bytes.
- [ ] Run `python -m pytest tests/test_upload_admission.py -q`; observe missing-feature failures before implementation.
- [ ] Implement dedicated contained path helpers, lock, bounded streaming/validation, immutable install and recoverable per-document admission intent; registry entries sharded by content id, no pipeline allowlist weakening.
- [ ] Run focused admission plus existing document/pipeline tests, then full suite; commit only verified code.

## Task 2: Authenticated streaming upload routes
**Files:** Create `src/selfos/web/routes/uploads.py`; modify route composition/actions; tests `tests/test_upload_http.py`.
**Interfaces:** POST `/__knowledge_upload__` consumes raw octet-stream, encoded `X-SelfOS-Filename`; GET `/__knowledge_uploads__` lists entries; both use existing local/auth guards.
- [ ] Add HTTP tests asserting raw bytes preserved, unauth/cross-origin denied before read, duplicate/conflicting/missing length and unsupported transfer encoding rejected, timeout/EOF cleanup, no downstream model calls.
- [ ] Observe RED; implement bounded stream wrapper and connection-close rejection, registry action delegation and explicit status codes.
- [ ] Run route/auth/admission regression; commit after checks.

## Task 3: Document normalization and bounded indexing
**Files:** Create `src/selfos/sources/upload_text.py`, `src/selfos/storage/upload_index.py`; modify `sources/documents.py`; tests `tests/test_upload_index.py`.
**Interfaces:** `index_document(vault, document_id, *, cancel, max_parts=2) -> dict`; `document_messages(vault, document_id, part_ids) -> list[dict]`.
- [ ] Test full redaction before fragmenting, quoted provenance, stable identities/ranges, empty eligible output, source hash changes, deterministic part continuation and crash-resume without part-zero overwrite.
- [ ] Observe RED; implement versioned normalized-text/index checkpoint with stable sealed parts, neutral document project scope and retained source locators.
- [ ] Test original viewing/cached metadata preservation and existing Harness parsing; commit verified indexing.

## Task 4: Selected organization and durable processing receipts
**Files:** Create `src/selfos/app/uploads.py`; modify knowledge/jobs, explicit transaction paths and migration; tests `tests/test_upload_organization.py`.
**Interfaces:** `upload_preview(vault, ids) -> dict`; `organize_uploads(vault, preview_id, ...) -> dict`; processing receipts reside in canonical transaction scope and reference committed parts/operation.
- [ ] Test selected-only no scanning, configured focus/detail, quoted facts not promoted, privacy/settings stale preview, cached zero-call repeats, cooperative stop, correction suppression, receipt commit/crash/restore and opted-in/out original migration.
- [ ] Observe RED; wire existing run_knowledge and shared job arbitration; publish receipts with canonical state and validate migration bounds.
- [ ] Run focused/full regression; commit only after transactional recovery evidence.

## Task 5: Picker/drop UI and complete acceptance
**Files:** Create upload template/script/styles and en/zh-CN upload locale; modify packaged manifest/dashboard source controls; tests `tests/test_upload_browser.py`.
**Interfaces:** existing dashboard source action opens upload dialog; status/list/upload/preview/organize actions reuse Tasks 2/4.
- [ ] Test keyboard picker/drop, 10-file cap/sequential transfers, upload progress/cancel, duplicate/history, auth expiry, locale/theme/mobile/focus, source view and selected organize with injected callbacks only.
- [ ] Observe RED; implement module-owned UI compatible with pending #49 interfaces; keep upload and organization controls distinct.
- [ ] Run full suite plus isolated Chromium; document supported formats/storage/privacy/recovery; independent whole-branch review, resolve confirmed findings, then implementation PR. Do not close #11 before full acceptance.
