# Model and Network Implementation Plan

**Goal:** Page-configured Anthropic and Chat Completions with shared proxy routing and a connection probe.

**Approved scope:** The user approved the model/network settings design in conversation and requested implementation.
**Architecture:** Python standard library adapters normalize existing Anthropic-shaped internal requests and responses. Configuration stays outside the vault; all model calls share routing.
**Constraints:** Preserve personal files and source conversations; no new dependencies; exclude secrets from Git and public responses. Existing linked worktree reused on a new branch from origin/main.

- [x] Write failing configuration/protocol tests and implement model_settings.py and model_client.py.
- [x] Write failing HTTP settings test, add local protected endpoints and active-import guard.
- [x] Route extraction, synthesis, support review, staging and chat through shared transport. Update test transport injection to new boundary.
- [x] Add model_ui.py, inject into existing served dashboard and generated dashboard.
- [x] Test both protocols with a local HTTP service and actual knowledge summarizer.
- [x] Run full regression and inspect rendered page: 589 passed; final transport correction verified by 14 focused tests; desktop/mobile save and reopen passed.
- [x] Document settings and install verified changes for local use: 21 files backed up and synchronized; new server on port 7150, import idle.

Review focus: blank/cleared keys, provider switches, nonstandard endpoints, local bypass and NO_PROXY, response truncation and malformed tool arguments.
Ruling: PAC and SOCKS are outside this implementation; page and guide state this explicitly.
Ruling: Keep existing source validation intact; connection probe verifies capability, not semantic quality.
