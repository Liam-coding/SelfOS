# Knowledge retention report implementation plan

> **For agentic workers:** Use superpowers:executing-plans; native execution authorized by user.

**Goal:** Explain retained, filtered, rejected, consolidated and missing knowledge with source-linked evidence.
**Architecture:** Bounded metadata report over corrected canonical state, diagnostics and journals. Instrument filtering and extraction metadata only.
**Tech Stack:** Python, pytest, existing packaged JavaScript/CSS and locale catalogs.
**Spec:** docs/superpowers/specs/2026-11-13-retention-report-design.md

## Global constraints
No personal runtime reads, paid calls, raw diagnostics, credentials or absolute public paths. Frozen acceptance5 unchanged. English default and Chinese parity.

## Review focus
Disabled sources suppress examples; legacy zeros remain uncertain; stopped staging stays separate; oversized/malformed metadata fails safely; recovered retries differ from unresolved failures.

### Task 1: Report and metadata
- [x] Write RED tests for canonical totals, transient filtering, category rejection, consolidation, invalid evidence, exclusions and bounded reads.
- [x] Observe expected missing-report failure.
- [x] Implement quality_report(vault) and metadata-only compaction/pipeline/journal instrumentation.
- [x] Run GREEN focused and pipeline regression tests.

### Task 2: Authenticated responsive UI
- [x] Write RED route, catalog parity and cached-dashboard integration tests.
- [x] Add GET /__knowledge_quality__, packaged shell and language-bound UI with encoded source links and job navigation.
- [x] Run GREEN HTTP/resource/i18n tests and synthetic browser verification.
- [x] Document units/limits and request root review before integration.

Validation: 103 focused and regression tests passed before the final correction-explanation addition; the final 17 report/auth/UI tests passed afterward. Synthetic Chromium smoke passed English 1280 and Chinese 390 layouts, live language switching and authenticated source reads (200). git diff --check passed. Root review/integration gate remains pending; no PR or merge.
