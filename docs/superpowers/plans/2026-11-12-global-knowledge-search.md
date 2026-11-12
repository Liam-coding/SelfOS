# Global knowledge search implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Implement issue #14 with global category search, optional project/source/date filters, matching excerpts and traceable source navigation.

**Architecture:** Extend the existing cached canonical library projection and authenticated endpoints. A focused text-search module ranks redacted visible fields deterministically; no parallel store, embeddings, source scans or model calls. Registered text-document evidence gets a contained immutable-source reader for the later #11 upload producer.

**Tech stack:** Python 3.10+, browser JavaScript, existing packaged JSON locales, synthetic pytest and browser fixtures.

**Spec:** https://github.com/Liam-coding/SelfOS/issues/14

## Constraints and decisions

- No private vault changes, full real conversation scans or live model requests. Preserve all five frozen acceptance files and existing source restrictions/authentication.
- Search canonical retained knowledge only; redact all public text before matching. IDs and absolute source paths are not searchable text.
- Split trimmed query on whitespace, require every distinct casefolded term, and prefer exact/phrase title matches then summary/decisions/evidence, with deterministic date and ID tie breaks. Empty query retains chronological browsing.
- Return a bounded actual matching excerpt and safe highlight ranges, category, attribution, project context and date. Query must not alter stored records.
- A project filter matches direct record project identity or associated evidence-source projects. It describes provenance context, never preference applicability scope. Public project filter IDs are opaque digests.
- Date ranges are inclusive YYYY-MM-DD and reject reversed/invalid ranges. Undated legacy history remains undated and does not match a date filter.
- Category counts for the current query/other filters are separate from overall canonical counts; selected categories and filters never silently reset during pagination or language changes.
- Source filters describe provider/type metadata; no original-source scan on search or filter load. Missing metadata is disclosed, not invented.
- Register uploaded text sources as source=uploaded_file with a resolved path under vault/.knowledge_uploads/originals, a content_sha256 and optional original_filename. Initial reader handles UTF-8 TXT/MD/JSON/JSONL, checks original-byte hash and containment, redacts output, and paginates original text. Binary formats receive a supported-format limitation until #11 adds extraction adapters; no upload or classification UI is built in this issue.
- Source errors use stable codes with localized UI feedback. Distinguish unsupported type, moved/missing original, changed content and denied location. Never follow arbitrary requested paths.

## Review focus

- One-term versus multi-term matching, Chinese text, evidence-only matches, long excerpts and redaction; stable pages for tied timestamps.
- Cross-project records: project context filtering must not broaden scope or hide valid categories.
- Source metadata absent/deleted and legacy unknown dates: consistent facet counts, unavailable explanations and no invented evidence.
- Delayed search/source responses after filters, language or dialogs change: stale results must not overwrite the current view; failed pagination remains retryable.
- Registered document escape via symlink, changed file/hash, invalid UTF-8, oversized input, malformed pagination and arbitrary unknown IDs: denied or clearly unavailable without exposing paths/content.

## Task 1: Search projection and filtering

Files: create src/selfos/knowledge/search.py and tests/test_global_knowledge_search.py; modify src/selfos/app/library.py and src/selfos/web/routes/dashboard.py; extend authenticated HTTP regression coverage.

- [x] Write and observe failing synthetic cross-category, rank/excerpt, project/source/date, unknown-date, validation, pagination and redaction tests.
- [x] Implement pure text matching/ranking/excerpts, add safe context/facet metadata to existing projection, and extend list_knowledge parameters project/source/date_from/date_to while retaining existing API behavior.
- [x] Pass filters through authenticated endpoint; prove cross-site and unauthenticated denial, stable pagination and no scans/model calls.

## Task 2: Original source navigation

Files: create src/selfos/sources/documents.py and tests/test_document_sources.py; modify app/library.py and dashboard routes.

- [x] Write and observe failing tests for immutable registered text documents, offset/limit, original filename, unsupported binary formats, missing/changed originals, malformed hash, redaction and escaping paths.
- [x] Add contained, hash-verified UTF-8 document source reader with bounded pagination and stable error codes. Preserve existing per-message conversation verification and restrictions.
- [x] Report missing recorded source references in detail responses. Return original content only for known registered source IDs; source context is distinct from exact quoted support.

## Task 3: Global search UI and verification

Files: modify web/rendering/library.py; create packaged en/search.json and zh-CN/search.json; add UI/HTTP tests and docs.

- [x] Write and observe failing actual-JavaScript tests for all-category default, filters, highlight rendering, pagination, preserved inputs on language switch, source errors and source text pagination.
- [x] Add accessible filters, visible category/context/matching excerpt, clear totals/empty/errors, and source limitations. Render only text/DOM nodes, never untrusted HTML.
- [x] Localize the complete search flow with English default; preserve current inputs/focus during translations and provide keyboard/mobile styling.
- [x] Verify actual generated dashboard with synthetic data on desktop/mobile, source/detail navigation, both languages and escaped excerpt text.
- [x] Run focused tests and full suite after stable implementation; verify wheel resources, frozen hashes, independent skill-required review and separate PR with Closes #14.


## Completed verification

Full suite: 657 passed (117.64s). Final independent review: 37 passed; publication-time focused rerun: 37 passed (11.97s). Actual authenticated desktop/mobile browser checks passed in English and Chinese. Built wheel imports and packaged locales verified. Five frozen acceptance hashes unchanged. Independent review findings resolved.
