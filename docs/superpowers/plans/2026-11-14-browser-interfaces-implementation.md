# Browser Interfaces Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Deliver #49 incrementally while preserving current workflows.

**Architecture:** Classic packaged scripts register private factories in a versioned runtime. A bootstrap initializes each owner once. Compatibility proxies remain until all callers migrate.

**Tech Stack:** Python package rendering, classic JavaScript, synthetic Node and Chromium fixtures.

**Spec:** ../specs/2026-11-13-browser-interfaces-design.md

## Global Constraints

No framework, bundler, new backend job protocol, real provider calls or personal source scans. No main merge. Read-only demo protections remain enforced. Intermediate PRs reference #49 without closing it.

## Tasks

1. Runtime and first owners: write RED lifecycle/dependency/rollback tests; implement singleton and cleanup; migrate theme/account/settings preserving draft races and auth redirects; update generated/cached delivery; run targeted and complete suites; synthetic Chromium checks; independent review; scoped PR.
2. Jobs and completion owners: RED tests for one stream, knowledge versus Harvest recovery, explicit stop, terminal event, teardown and polling; migrate jobs/import settings/usage/publication/completion subscriptions; verify existing backend contracts; separate PR.
3. Remaining owners: RED overlap and history tests; migrate chat/dimensions, knowledge/corrections/timeline, staging/overview/privacy/onboarding/sparklines and scoped actions; exact compatibility map; full synthetic matrix, package and legacy-page checks; separate PR that closes #49 only after all acceptance passes.

## Review Focus

Cached custom scripts and unknown action attributes must survive refresh. Initialization performs reads only. Credential drafts never serialize. Teardown must not mutate server jobs. Partial delivery must state all remaining owners and acceptance gaps.

## Execution Ledger

Runtime RED: missing ui-runtime.js; GREEN: dependency preflight, cycle, repeat delivery, incompatible versions and rollback test passed.
Theme RED: missing theme API; registration now inert with one language subscription and teardown.
Account RED: fetch changed at evaluation; registration now inert and the shared request owner initializes one fetch wrapper before dependent modules.
Stage-one targeted verification: 11 passed, including real local Chromium model-list races, nested action clicks, account confirmation validation, theme/locale changes, three init calls, repeated owner delivery, active-request cancellation, stale-response suppression, busy replacement rejection and safe explicit remount.
Stage-one whole-suite checkpoints: 1063 passed / 5 skipped before review; 1064 passed / 5 skipped after review and modal-remount fixes. A startup-order regression test then proved that the request boundary must mount before legacy readiness reads. Bootstrap now binds readiness in the head, and the remaining import/staging initial reads run at readiness. The staging test fixture needed an explicit DOMContentLoaded dispatch; its full-suite failure was reported and the corrected fixture passed targeted verification. Latest whole suite is running in stage-one-verified.log.
Installed wheel: selfos-0.5.0 built; imports from an extracted wheel outside repository cwd, package resources, generated dashboard and three cached refreshes passed.
Independent reviewer: browser_stage_one_review reported three Important findings (custom owner deletion through body-text matching, root replacement silently accepted, account requests not aborted) and a missing exact legacy-handler upgrade. All four reproductions were RED before fixes. Root identity checks, account request controllers, opening-tag ownership parsing and exact theme handler migration now pass targeted tests. Additional safe-remount draft test was RED and now passes.
Installed-wheel browser verification: the extracted package passes the same real Chromium lifecycle/draft/remount checks and three cached refreshes outside repository cwd. Review artifacts are retained under work/installed-browser-ym8t_sjc; an earlier temporary-directory cleanup hit a Windows Chrome file lock after browser assertions passed, so the final verification retains its owned artifact directory.
Native modal remount RED: cloned open dialogs lost top-layer focus semantics; safe draft restoration now closes/reopens modal dialogs explicitly and the Chromium :modal assertion passed.
Stage one verified: python -m pytest -q -> 1065 passed, 5 skipped (stage-one-verified.log). All Important review findings fixed by RED/GREEN tests; no deferred minors. Wheel build and installed-package real Chromium/cached refresh checks passed. No model calls, private vault scans or main merge were performed. Next: publish scoped stage-one PR, then execute stages two and three on stacked branches.
Ruling: Deliver the approved design in its three staged PRs; this branch covers the first owners, not full #49. Cost if wrong: remaining modules retain legacy re-delivery limitations until following PRs.
Ruling: module(id) can instantiate its DOM/I/O-free factory before mounting to preserve existing test and compatibility callers. init still preflights the complete graph before mounting. Cost if wrong: a consumer might call a mount-dependent API before the DOM exists; ordinary event handlers run after readiness.
