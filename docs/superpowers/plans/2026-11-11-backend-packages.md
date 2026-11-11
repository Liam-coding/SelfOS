# Backend Packages Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task, with one fresh review at the end.

**Goal:** Implement backend Issue #6 with clear package boundaries and compatible commands and data.
**Architecture:** A src/selfos package separates source ingestion, knowledge domain rules, storage, providers, application orchestration, security and HTTP routes. Legacy modules are compatibility entry points only; package code never imports them. Shared contracts remove cycles rather than hiding them behind function-local imports.
**Tech Stack:** Python, setuptools, pytest, standard-library HTTP server, argon2-cffi.
**Spec:** https://github.com/Liam-coding/SelfOS/issues/6 and the approved backend scope in this conversation.

## Global Constraints
- Preserve existing command flags, vault formats, settings, provenance, backups, checkpoints and authentication protections.
- No full production import or conversation scan; use temporary fixtures.
- Frontend refactor remains Issue #30; preserve rendering strings and browser behavior.
- Data root is explicit and independent of package resource location; legacy commands use their checkout root.
- Domain and storage never import application, CLI or server modules. Package imports must be acyclic, including local imports.
- Never modify private vault or real credentials; commit only explicit project paths.

## Review Focus
- Commands from another working directory must use the intended root.
- Installed wheel must include authentication locale and onboarding resources.
- Legacy import and monkeypatch consumers must reach the actual owning module.
- HTTP task launches must work without root script files after installation.
- Cancellation, rollback and authentication fail-closed behavior must survive extraction.

### Task 1: Package boundaries and compatibility
**Files:** src/selfos/{sources,knowledge,storage,providers,app,security,web}/; root Python wrappers; pyproject.toml; tests/test_backend_architecture.py.
**Interfaces:** Shared text helpers in sources/text.py; JSON contracts in knowledge/contracts.py; storage primitives in storage/files.py; session compaction in sources/compaction.py; application use cases consume these modules. Legacy import proxies forward symbols and assignments to their owners.
- [ ] Add tests for package availability, legacy function identity and one-way acyclic imports; watch them fail.
- [ ] Extract by responsibility, rewrite all imports to symbol owners, retain legacy wrappers. Separate harvest ingestion, workspaces, scoring, rendering and CLI; separate knowledge contracts, providers, storage, rules and orchestration.
- [ ] Run architecture tests and full regressions. Expected: all pass, frozen eval fixtures unchanged.

### Task 2: Explicit paths and installable commands
**Files:** src/selfos/paths.py; src/selfos/app/cli.py; package resources; pyproject.toml; tests/test_backend_paths.py.
**Interfaces:** AppPaths.from_root(root) resolves vault, config, auth marker and dashboard; project_root() honors SELFOS_ROOT, defaults to cwd for installed commands, and legacy wrappers set checkout root only as default. Entry points selfos-serve, selfos-knowledge, selfos-harvest, selfos-auth retain old flags and add --root.
- [ ] Add tests for foreign cwd, explicit root, locale resources and CLI help; watch failures.
- [ ] Centralize paths, package only public onboarding resources, replace HTTP script launches with package module commands and propagated root.
- [ ] Build/install wheel in isolated target and run commands from a temporary cwd. Expected: successful help and correct root without scanning/model calls.

### Task 3: Thin HTTP composition and task boundaries
**Files:** src/selfos/web/server.py; src/selfos/web/routes/{auth,protocol,dashboard,actions}.py; src/selfos/app/{jobs,chat}.py; tests/test_backend_architecture.py.
**Interfaces:** Route mixins consume handler.runtime supplied by composition root; job helpers consume explicit run state, lock and heartbeat; chat context consumes explicit vault.
- [ ] Add tests that routes do not import server and services do not import routes; assert handler methods live in route modules. Watch failure.
- [ ] Split handlers without changing route behavior; preserve legacy runtime globals for existing callers.
- [ ] Run HTTP/auth/stream tests and full regression. Expected: all pass.

### Task 4: Documentation, review and delivery
**Files:** docs/backend-architecture.md; README links; targeted regression tests.
- [ ] Document module ownership, import rules, resource/data paths and commands.
- [ ] Verify full suite, wheel installation, frozen fixture bytes and diff privacy.
- [ ] Obtain fresh whole-branch review; resolve material findings with regression tests.
- [ ] Commit explicit paths and create an English PR closing #6 only. Keep private installation separate until verified.
