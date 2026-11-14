# Knowledge Question Answering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Answer knowledge questions from bounded retained records with usable, provenance-aware citations.
**Architecture:** Pure retrieval/output rules consume the existing corrected/privacy-filtered library projection. An app service owns state revisions and provider calls; the existing private chat owner composes knowledge questions and source navigation without a second import pipeline.
**Tech Stack:** Python 3.10+, standard library HTTP, existing provider adapter and request-usage journal, package resources, vanilla JavaScript, pytest/Chromium.
**Spec:** docs/superpowers/specs/2026-11-15-knowledge-qa-design.md

## Global Constraints

- At most 2,000 question characters, 100 project-ID characters, 8 records, 12,000 record-text characters and 24 evidence references.
- At most 2 model requests including repair; token accounting only, no prices.
- English default with complete Chinese translations.
- No paid model calls, personal conversation scans, new dependency or price calculations.
- Model prose is interpretation; citation membership is not semantic entailment proof.

## Review Focus

- Unsupported compound questions must not borrow unrelated personal facts (Task 1).
- A privacy or manual-correction change during a response must suppress outdated output (Task 2).
- A citation from an old answer must not silently navigate to revised knowledge (Task 2).
- A cancelled request or old cloned DOM must not append a late answer (Task 3).
- Old programmatic score/general-chat paths must remain functional (Task 3).

### Task 1: Deterministic retrieval and typed attribution

**Files:** Create src/selfos/knowledge/qa_retrieval.py, src/selfos/knowledge/qa_output.py, tests/test_knowledge_qa_retrieval.py and tests/test_knowledge_qa_output.py.
**Interfaces:** retrieve_records(records, question, project='') -> list of bounded record/detail/source projections; validate_answer(payload, selected) -> normalized status/summary/references/inferences, with server-derived provenance. Inputs are library _records tuples; no disk or network in either rule module.

- [x] Write failing fixture tests for English/Chinese natural questions, current/history distinction, completed work, unsupported questions, project scope and the exact global caps.
- [x] Run retrieval tests; verify missing interface/behavior failures.
- [x] Implement deterministic field ranking and bounded evidence selection; unknown specific questions return empty selection.
- [x] Write failing output tests for unknown IDs, empty answered references, inferred/provided provenance confusion, insufficient-evidence status, invalid types and bounds.
- [x] Implement typed output validation and server-owned citations; literal record evidence never comes from model-generated quotation text.
- [x] Run both test files and commit the independently testable rules.

### Task 2: App, provider, authenticated API and revision validation

**Files:** Create src/selfos/app/knowledge_qa.py, src/selfos/providers/knowledge_qa.py, tests/test_knowledge_qa_service.py, tests/test_auth_knowledge_qa.py and tests/test_knowledge_qa_transport.py; modify web/routes/actions.py and dashboard.py.
**Interfaces:** question_context(vault) -> filtered project metadata; answer_question(vault, config_root, question, project='', locale='en', answerer=None, cancel=lambda:False) -> structured reply/citations; validate_citation(vault, record_id, revision) -> current matching record. Provider answerer consumes bounded selected records and feedback and uses existing request_opener/RequestUsage. Routes: GET /__knowledge_qa_context__, POST /__knowledge_qa__, GET /__knowledge_qa_citation__.

- [x] Write failing synthetic service tests for current corrections/preferences/privacy projection, no-model unsupported answers, policy/knowledge changes, stale citations and at-most-two repair calls.
- [x] Implement composition of library _state/_records with privacy.model_state, revision seals, rules from Task 1 and localized result states.
- [x] Add loopback transport tests for Anthropic and OpenAI-compatible calls, forced structured output, request allowance and provider-reported token accounting; implement provider using the existing adapter.
- [x] Add real-gate authenticated/same-origin/body-bound API tests; implement only the three scoped routes and generic error codes.
- [x] Run service/transport/auth plus relevant existing privacy/correction/chat tests and commit.

### Task 3: Private chat composition and delivery

**Files:** Modify resources/web/scripts/dashboard-chat.js, templates/dashboard-page.html, styles/dashboard.css, web/rendering/refresh.py as required; create private scripts/knowledge-qa.js helper, locales/en/qa.json, locales/zh-CN/qa.json, tests/test_knowledge_qa_browser.py; update manifest and docs/knowledge-qa.md/both READMEs. Extend knowledge-browser navigation only where needed for a validated source target.
**Interfaces:** Existing chat send/open/snapshot facades stay compatible; ask(question, project='') uses Task 2 and renders bounded summary/citation/inference DOM. Chat remains sole owner of composer/messages; helper has no writable global state. Existing knowledge detail/source owner performs navigation after Task 2 revision validation.

- [x] Write failing actual-browser tests for en/zh, project choice, source/correction/history labels, hostile model text, one pending send, cancel/remount, stale citations and existing programmatic conversation behavior.
- [x] Implement knowledge-mode default for ordinary question input, explicit conversation mode, localized controls and request cancellation; do not send old knowledge answers back as conversation context.
- [x] Render citations from server metadata and validate revision before using the existing source viewer. Preserve drafts and structured messages after cloned remount; repair cached page controls without duplicates.
- [x] Run focused browser/API regressions, independent installed-wheel/resource/three-refresh checks, then full pytest with Chrome.
- [x] Dispatch one fresh whole-branch reviewer; fix Critical/Important findings with RED/GREEN and relevant green regressions.
- [ ] Publish English dependent PR (base feat/import-center while #84 is open), closing #18 only when criteria delivered. Continue #83; keep the broad issue-resolution goal active.

### Review fixes and verification in progress

- One fresh read-only whole-branch reviewer found two Important issues: overview scaffolding could select completed keyword archives, and QA revisions were not carried into source/text pagination. Both were reproduced RED and fixed GREEN.
- Overview normalization now removes recognized scaffolding while retaining specific qualifiers; current-project intent consistently filters active statuses. Eleven additional overview/qualifier cases were added.
- The detail owner retains the QA record revision for source and source-list continuations. The server validates record revision and source membership before and after building source responses. Native browser tests cover mutation after opening, before text pagination, before source-list pagination and between detail/source requests.
- Minor envelope-shape and provenance-label findings were also fixed. Anthropic/OpenAI loopback fixtures cover invalid IDs, malformed tool JSON, and list/null/scalar envelopes; incomplete provider usage remains explicitly incomplete.
- Corrected/native-browser/API/resource regression set: 66 passed. Additional legacy interface/catalog/privacy/correction set: 95 passed with two old chat tests corrected to explicitly select Conversation; their failure/translation assertions are retained. The resulting chat/QA/transport set passed 17 tests.
- Final full regression and independent reviewed-wheel verification passed. Publication remains unchecked until the PR is created.
- Reviewed wheel SHA-256: 8778e4ca5db393f2c601cfb58b4ed2627f0a929f51ae04179d8acb3f3c3155e8. Separately installed smoke verification passed with 71 resources, three cached refreshes, both locale catalogs, actual project-context scoping, an unsupported no-model question, unchanged canonical bytes and privacy-invalidated citations. The initial smoke assertion assumed a raw project ID; it was corrected to use the library's returned stable project-context ID.
- Final complete Chromium-enabled suite on a5ed652: **1493 passed, 7 skipped in 558.83 seconds**, exit 0. No assertions were weakened, no blanket retries added and no private data or paid provider calls used. Windows transcript: work/knowledge-qa-final-full.log in the external task artifact workspace.
