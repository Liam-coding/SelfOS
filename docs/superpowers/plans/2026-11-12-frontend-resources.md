# Frontend resource refactor implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Implement #30 by moving maintained HTML, CSS and browser responsibilities out of Python strings while preserving current rendered output and access behavior.

**Architecture:** Python rendering adapters load allowlisted packaged templates/assets through importlib.resources. Templates include separate stylesheet and script resources; dashboard data uses explicit one-pass placeholders rather than runtime Python expression evaluation. Rendered responses remain self-contained: no static filesystem-serving endpoint is introduced.

**Tech stack:** Existing Python 3.10+, HTML/CSS/JavaScript, setuptools package data and synthetic pytest/browser fixtures; no framework or new dependency.

**Spec:** https://github.com/Liam-coding/SelfOS/issues/30

## Decisions and constraints

- Use the existing isolated selfos-pr worktree and a fresh branch from main. Preserve private vault, originals, configuration, auth storage, checkpoints and all five frozen acceptance files. No live models or full production imports.
- Move page, score card, overview, knowledge browser, import controls, model/network/settings, login/account and chat UI source to resources/web/templates, styles and scripts. Keep Python data construction and component integration in web/rendering.
- Resources are selected only by an explicit package manifest; reject unknown, absolute and traversal names. Load from the installed package, independently of checkout/CWD. No arbitrary local file route, no vault/resource overlap, and no public data or config endpoint.
- Retain inline rendered assets for standalone dashboard compatibility and existing auth boundaries. Login gets only its own resources; dashboard remains authenticated. Document this serving policy rather than adding an unnecessary public asset route.
- Preserve output bytes for representative pages/components using a synthetic pre-refactor snapshot. Preserve existing script evaluation order, global compatibility entry points, event hooks and API/SSE contracts. Do not change application behavior in structural work.
- Split the dashboard browser source by cohesive responsibilities (theme/language, dimensions/charts, chat, import/progress and staging) while keeping their assembled script scope/order. Existing focused settings/auth/browser modules keep their names and interfaces.
- Shared visual tokens live in the visual-system stylesheet; dashboard compatibility layout, component styles and overrides have explicit ownership and cascade order. Avoid duplicating rules during extraction. Remove a redundant rule only when output/browser equivalence is proven.
- Template substitution is single-pass over explicit values. Asset/template directives are resolved before values, so user values never become resource names, Python expressions or further placeholders. Existing escaping responsibility remains at current renderer/API boundaries.
- Prepare locale injection points and preserve current language behavior; full translation cleanup belongs to #7. Retain keyboard, reduced motion, desktop/mobile and light/dark behavior.

## Review focus

- Script order/global scope after file splitting, including initialization listeners, fetch wrapping, progress and stop controls.
- Resource include/value substitution collisions, missing/unknown names and package/CWD independence.
- Login public output versus authenticated page data; no new filesystem/static exposure.
- CSS cascade and responsive/dark/reduced-motion behavior across components; no duplicate styles introduced.
- Installed wheel resources and a dashboard cached before refactor; existing replacement helpers still recognize and update components.

## Task 1: Resource loader and compatibility baseline

Files: create web/rendering/resources.py, resources/web/manifest.json, tests/test_frontend_resources.py and tests/fixtures/frontend_rendering_baseline.json; modify pyproject.toml package-data.

Interface: frontend_text(name) expands only allowlisted package includes; render_ui(name, values) substitutes explicit value markers once. Neither reads a vault or evaluates expressions.

- [x] Capture deterministic synthetic dashboard/component hashes before extraction.
- [x] Write failing tests for missing loader/resources, traversal/unknown names, include cycles, value-as-directive injection and independent CWD.
- [x] Implement loader and packaging, then pass targeted tests.

## Task 2: Extract templates and component assets

Files: modify all current web/rendering UI adapters; add resources/web/templates/*.html, styles/*.css and scripts/*.js.

- [x] Add architecture tests that fail on large embedded UI literals and compare generated page/component hashes with the original baseline.
- [x] Extract static fragments and f-string templates once, retaining explicit Python expressions at their existing callsites as rendered values. Split stylesheet/script bodies into their own package resources.
- [x] Split dashboard script into functional source modules in the existing order and document shared globals/cascade ownership. Pass byte-compatibility and existing focused UI/auth tests.

## Task 3: Browser, package and contracts

Files: docs/frontend-architecture.md, README.md, README.zh-CN.md and focused frontend/auth tests.

- [x] Document component ownership, placeholders, rendering/asset access policy, API/auth/SSE contracts and locale extension points.
- [x] Verify synthetic actual generated dashboard and login/account/settings/chat/import UI in English/Chinese, desktop/mobile, light/dark and reduced motion. Do not perform real imports or model calls.
- [x] Build and import installed wheel from another CWD; verify all resources and frozen hashes.
- [x] Run full suite, obtain skill-required independent review, fix findings and create separate English PR. Closes #30 only after all current production UI is migrated and acceptance passes; no auto merge.


## Completed evidence

Final full suite: 626 passed in 99.55s; focused resource/auth6 passed and independent review found no actionable defects. Eleven pre-refactor outputs are byte-identical; independent direct original/current comparisons also covered four extra dashboard score variants and marker-looking synthetic display values. Actual browser checks passed for login/password changes, dimensions, source browsing, model/proxy saving, scripted chat and import stop/resume/reload, both languages, desktop/mobile, light/dark and reduced motion. Installed-wheel imports, all assets, rendering baseline and five frozen hashes verified. No private data changes or live model/import calls. Browser harness corrections used the actual manual proxy option and awaited the stop acknowledgement before emitting a terminal fixture event; no product behavior changed.
