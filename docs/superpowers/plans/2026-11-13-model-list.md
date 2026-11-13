# Available Model Discovery Implementation Plan

> **For agentic workers:** Execute natively with superpowers:executing-plans; parent coordinates independent review.

**Goal:** Implement authorized issue #46: load available models in Model and network settings with one click.

**Architecture:** Resolve current draft settings using existing validation without writing configuration. Fetch metadata through a shared provider opener, then expose an optional select beside the editable model name. Ignore responses after provider/network/key changes or dialog closure.

**Tech Stack:** Python standard library HTTP transport, native JavaScript, existing locale catalogs and CSS.

**Spec:** GitHub issue #46 and parent task requirements.

## Global Constraints

- No model generation, live provider calls, personal conversations, or private repository reads.
- Keep saved API keys server-side; draft discovery must not save or erase settings.
- English by default, Chinese through existing locale catalogs; preserve manual model entry.

## Review Focus

- Provider changes must not reuse a different provider's saved key.
- Draft edits and dialog reopen must invalidate pending discoveries.
- Empty, malformed, unavailable and unsupported providers need recoverable feedback.
- Model identifiers render as text and must not execute markup.
- Mobile viewport must retain accessible controls without horizontal overflow.

### Task 1: Draft metadata endpoint

Files: providers/settings.py, providers/client.py, web/routes/actions.py, tests/test_model_list.py.

- [x] Write HTTP recording tests for endpoints, auth, draft isolation, empty/error and validation cases.
- [x] Run tests and observe missing endpoint failures.
- [x] Extract resolve_config(root, patch) and provider_opener(config, url); implement list_models(root, patch) returning models.
- [x] Verify new and existing transport/settings tests.

### Task 2: Discovery and selection UI

Files: settings-model.js/html/css, en/ui.json, zh-CN/ui.json, tests/test_model_list_browser.py.

- [x] Write synthetic browser test for draft preservation, selection, locale, stale/closed requests, empty/error feedback and mobile layout.
- [x] Observe failure on missing discovery control.
- [x] Implement explicit discovery control, editable name, optional select, localized status, invalidation and loading handling.
- [x] Run relevant browser and complete pytest suite; inspect diff and commit.

## Verification

- Fresh full suite: 962 passed in 274.88 seconds.
- Synthetic Chromium checks passed for discovery drafts, selection, loading, locale changes, empty/unsupported/error results, stale responses, close/reopen, and a 390-pixel viewport.
- Initial full run recorded an existing stop/resume readiness race and an earlier browser fixture timeout; the unchanged stop/resume test passed separately and the fresh full suite passed after the fixture was finalized.
- No live provider calls or personal conversation reads were used.
