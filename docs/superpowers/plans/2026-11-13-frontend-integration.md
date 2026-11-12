# Frontend integration implementation plan

Use superpowers:executing-plans inline. Spec: docs/superpowers/specs/2026-11-13-frontend-integration-design.md.

**Goal:** reproducibly validate merged app workflows for #47 and fix confirmed regressions.

**Architecture:** optional Playwright CLI harness, synthetic temporary app and sources, local deterministic model HTTP fixture, test-only discovery bootstrap around the real knowledge CLI. No production test hooks.

## Review focus

- Child never performs default local source discovery.
- Source bytes and stopped checkpoints remain intact through reload/resume.
- Unsaved forms and active task identities survive language changes.
- Installed wheel is actually imported from the provided package directory.
- Failure cleanup terminates child/server and no external model requests occur.

### Task 1: reusable fixture and integrated browser runner

Create tests/browser/integration_fixture.py (synthetic source/state creation and bounded local model fixture) and tests/browser/frontend_integration.py (CLI, real app server, scenarios, screenshots/report). Optional browser dependencies do not run under ordinary pytest collection.

Interfaces: integration_fixture.create_profile(root: Path) -> dict with vault, source_root and original_bytes; ModelFixture(started/extraction_gate events, requests list) exposes a loopback base_url and context-managed cleanup. frontend_integration.py consumes --browser, --output and --package-path, runs fixtures via installed or checkout package, exits nonzero for any workflow failure and writes results.json. --worker SOURCE_ROOT forwards remaining arguments to selfos.app.knowledge_cli.main after restricting discovery to SOURCE_ROOT.

- [x] Write scenario assertions: unauthenticated API blocked; wrong password stays signed out; keyboard Overall scrolls to dimensions; model form values/focus retained; successful/failed local model test; search and timeline pagination change displayed rows; raw sources remain readable.
- [x] Run against merged main; report exact failing workflow when encountered.
- [x] Add actual child SSE workflow: wait for first saved checkpoint, gate second response, change locale/reload, request stop, release gate, assert stopped/checkpoints, resume, assert publication and original source bytes.
- [x] Run desktop/mobile and theme/locale/motion matrix with pageerror/network guards; fix confirmed production defects only after focused failing regression tests.
- [x] Commit passing runner and fixtures.

### Task 2: installed wheel and report

Modify docs/frontend-architecture.md to link reproducible command; create docs/frontend-integration-validation.md with commit/results/platform limits.

- [x] Build wheel via pip wheel --no-deps --no-build-isolation; install into temporary target.
- [x] Run same harness from foreign cwd with --package-path target and validate selfos import origin.
- [x] Record wheel hash, browser/Python versions, screenshots and per-workflow output without synthetic credentials.
- [x] Full pytest, diff check, frozen input check and one independent whole-branch review; fix Important findings through RED/GREEN.
- [ ] Publish English PR closing #47 only once all required workflows pass; CI then merge.
