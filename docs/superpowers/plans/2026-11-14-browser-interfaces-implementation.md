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

Stage two base: 01c119f, stacked after stage-one PR #78 (https://github.com/Liam-coding/SelfOS/pull/78). Jobs, import-settings, usage and publication are now private factories with controlled requests, scoped actions, lifecycle cleanup and one job subscription per mounted owner. RED/GREEN tests proved one stream, one knowledge stop, mutex, terminal notification, kind-specific disconnect handling, abort-only teardown, stale suppression and status recovery. Chromium RED/GREEN additionally proved no duplicate budget POST, ignored prototype-named actions and retained import drafts after three init calls plus repeated owner delivery.
Completion-owner RED: repeated init produced no registered quality/overview startup/subscriptions. GREEN: quality and overview read once, coalesce active refresh, abort requests and remove subscriptions on teardown. Both refresh only on knowledge completion.
Staging RED: metadata reorder changed the selected row's filename submitted to apply. GREEN: literal filename belongs to its row, metadata refresh preserves mounted rows, locale changes preserve selection/pending apply and operation failures. Staging subscribes to all job completions to preserve Harvest success refresh.
Onboarding RED: runtime initialization omitted its startup read and input listeners. Migrated owner now retains private draft state, cancellation/generation guards and explicit save-sources before step advancement. Completion subscription retains dirty source drafts.
Ruling: Completion subscriptions and their lifecycle owners are migrated together in stage two, including staging/overview/onboarding otherwise named again in stage three. This avoids mixing new jobs notifications with legacy unowned listeners. Cost if wrong: stage-two review is larger; remaining stage-three action consumers still use stable proxies.
Ruling: publication calls import-settings only in post-init user callbacks, so it does not declare that reverse dependency; import-settings declares publication. This avoids a cyclic initialization graph. Cost if wrong: an isolated publication-only page cannot execute resume without the import-settings owner; complete dashboard delivery includes it.
Stage-two full-suite checkpoint before existing fixture migration: 1063 passed, 5 skipped, 3 failed (old runtime-less import/publication fixtures). Adapted all three through production public interfaces, preserving the same workflow assertions; 8 targeted tests passed.

Stage-two native verification: real Chromium EventSource loopback fixture passed. Three init calls and repeated jobs/import-settings/usage/publication/quality/overview/staging/onboarding delivery created no duplicate reads, streams or usage interval. Explicit stop coalesced into one POST, cancellation emitted one terminal event, Harvest failure made no knowledge-status recovery reads, knowledge disconnect recovered via GET, teardown made no stop POST, remount opened no replacement stream, and successful recovery cleared the interval. Dirty import and source drafts survived completion.
Stage-two full-suite checkpoint: 1068 passed, 5 skipped (stage-two-full.log). Newly added exact cached job/staging handler RED/GREEN test passed separately. Wheel build and extracted-package native SSE, model/remount browser and three cached refresh checks passed outside repository cwd.
Final review: independent browser_stage_two_review found one Important and two Minor. Important pending-open settings loading reproduced RED, then fixed with resumed status GET and enabled controls, tested on unchanged and cloned roots. Chinese custom-domain delimiter finding regraded Important because it changes saved user input: research plus fitness becomes one domain and question marks unexpectedly split values. Both comma forms and literal question mark reproduced RED, restored original delimiter GREEN.
Final: minor (deferred): Loading/success/warning progress icons are literal question marks; textual localized phase labels remain correct. Restore original symbols during the remaining styling pass.
Ruling: Pending settings loads resume one GET after explicit remount, instead of simply enabling unpopulated settings. The old response remains generation-invalid and aborted. Cost if wrong: remount requires one extra metadata read, but never restarts an import or sends a model request.

Final: fixed pending settings loading after teardown/remount - test_teardown_pending_settings_read_restores_enabled_draft_on_remount[False/True] RED/GREEN, suite 1071 passed / 5 skipped (stage-two-final.log). Both comma forms and literal question mark now pass the same fixture. Final extracted-wheel native SSE, model lifecycle, pending import read/remount and three cached refresh checks passed under work/installed-stage-two-fixed.
Stage two complete: all Important findings fixed and final full suite green. One deferred icon minor remains for stage-three styling; no main merge, provider request or personal scan. Continue remaining owners and final #49 acceptance on the next stacked branch.
