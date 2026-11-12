# Integrated frontend validation

Implement issue #47 against merged main, beginning at 4561dfa. The user authorized sequential execution after #40/#38/#15. This is a reproducible test/report deliverable; fix confirmed defects without redesigning unrelated UI.

## Approach

Use the existing Python app and real Chromium, rather than simulated DOM assertions alone. Run an authenticated ThreadingHTTPServer over a temporary synthetic app/vault. A local OpenAI-compatible HTTP fixture handles model test, chat, extraction and refinement requests; no paid endpoint is configured. A test-only child bootstrap restricts source discovery to its temporary fixture directory, then invokes the real knowledge CLI, preserving subprocess, SSE, stop-file, checkpoint and publication behavior. This transport/discovery substitution is explicit in the report.

Produce a script in tests/browser/frontend_integration.py with --browser, --output, and --package-path options. Package-path loads an independently installed wheel from a different cwd; refuse an imported selfos outside that directory when supplied. Test utilities live under tests/browser, never production modules.

## Workflows

- Real login/logout, wrong password and protected API; default English, switch to Chinese.
- Overall keyboard navigation reaches dimension cards. Model/provider/network configuration persists; invalid local model response produces actionable feedback; successful local test and unsaved input survive language change.
- Search across synthetic categories, filters/pagination, original-source reading; project timeline filters and pagination.
- Real knowledge CLI/SSE with two synthetic sessions: first checkpoint, blocked local fixture response, language switch, reload/status recovery, stop, release pending response, then resume and published result. Assert checkpoint/source integrity.
- Desktop/light/English/normal motion and mobile/dark/Chinese/reduced motion, plus opposite locale/theme pairings. Assert no horizontal overflow, page errors, lost keyboard focus or duplicate tasks after language changes.

The local fixture uses deterministic event gates with bounded timeouts rather than timing guesses. Every outbound browser URL must be the app or local fixture origin; source directory is explicit and no default home discovery runs. Secrets are synthetic. Browser server, contexts and children are cleaned up on failure.

## Evidence

Report tested commit, Python/browser/platform, wheel hash/path, per-workflow results and screenshots. Different-cwd installed-wheel execution must run the same workflows. Full pytest remains required before PR. Windows/Chromium evidence is not macOS/Safari validation. Existing macOS CI limits remain documented.

## Builder choices

Use Playwright already available outside the repository; keep it optional for ordinary unit tests. Place this heavier browser workflow behind an explicit command rather than adding it to every PR CI run. Seed enough synthetic timeline/search records to require pagination. No source-only or model-quality test result is presented as integrated browser evidence.
