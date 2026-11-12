# Frontend structure

SelfOS keeps its existing HTML/CSS/JavaScript UI. Python builds page data and combines packaged resources; it no longer maintains the dashboard and component bodies as large Python literals.

## Resource ownership

All maintained UI source lives under src/selfos/resources/web:

| Area | Templates | Styles | Browser source |
| --- | --- | --- | --- |
| Dashboard and dimension cards | dashboard-page.html, dashboard-card.html | dashboard.css | dashboard-theme-language, dimensions, chat, imports, sparklines and staging scripts |
| Shared visual system and overview | visual-system.html, overview.html | visual-system.css | overview.js |
| Knowledge browsing and original sources | knowledge-browser.html, knowledge-browser-style.html | knowledge-browser.css | knowledge-browser.js |
| Import settings and recovery actions | import-controls.html | Existing shared controls | import-controls.js |
| Published knowledge and saved progress | import-publication.html | import-publication.css | import-publication.js |
| Project chronology and source paging | project-timeline.html | project-timeline.css | project-timeline.js |
| Settings, model and proxy configuration | settings-model.html | settings-model.css | settings-model.js |
| Login and account controls | login-head/form/tail, auth-style/script, account-controls/script | login.css, auth.css | login.js, auth-common.js, account.js |

The Python adapters in selfos.web.rendering retain their existing public constants and functions. They load these resources and construct explicit dashboard values such as label_zh, hist_json, greeting_en and cards_html. Existing component-replacement helpers still operate on the assembled markup, including dashboards generated before this refactor.

## Loading and template contract

manifest.json lists every allowed template, stylesheet and script. The resource loader uses importlib.resources, so installation and a different working directory do not redirect it to checkout files or a user vault. Unknown, absolute and traversal names are rejected. Include cycles are rejected.

A template includes a declared resource using **@@SELFOS_RESOURCE:name@@**. Dashboard values use **@@SELFOS_VALUE:key@@**. Includes resolve before values; value replacement runs once. A value containing another placeholder or resource directive remains literal data. No Python expression is evaluated from a template, and a missing value is an explicit error. Rendering adapters retain responsibility for the distinction between trusted assembled component markup and display data; this structural change does not introduce a new user-template engine or change existing escaping behavior.

Resources are composed into the same self-contained HTML responses as before. There is no new public static-file endpoint and no route that maps a requested filename to the filesystem. Login resources are public only as part of the login response. Dashboard data, knowledge APIs, model configuration and processing streams retain their existing login/local-origin checks. Credentials, vault contents and model settings are not package assets.

## Browser contracts and execution order

Dashboard source files are cohesive browser modules assembled in their original order inside the existing script scope. They are source modules, not ES-module network imports; this preserves offline/generated HTML and existing onclick entry points.

1. Theme/language owns isDark, lang, toggleTheme, toggleLang and the selfos-language event.
2. Dimensions owns openDim and dimension-to-chat actions. Its chat helper calls the chat functions defined later, after script initialization.
3. Imports owns confirmHarvest, stopKnowledge and recoverKnowledgeRun, SSE progress and reload attachment.
4. Chat owns chatHistory, appendMsg, sendChat, toggleChat and keyboard input.
5. Sparklines render score history after the page exists.
6. Staging owns its review list, selection and apply actions.

Standalone browser/settings/auth resources retain their existing global compatibility functions or IIFE scopes and initialization listeners. Account code wraps fetch for session-expiry handling after the dashboard script is defined, as before. New code should extend its owning file, rather than add another cross-cutting dashboard script. Locale migration under #7 can replace text in those owners or inject packaged locale data at their existing hooks; full translation behavior is not changed here.

## API and lifecycle boundaries

| UI owner | Backend contract |
| --- | --- |
| Knowledge browser | Authenticated GET /__knowledge__, /__knowledge_item__, /__knowledge_source__; category/query/pagination and registered source identities |
| Project timeline | Authenticated GET /__knowledge_timeline__; project record ID, milestone filters, pagination and revision-aware refresh; original sources retain the shared paging contract |
| Import controls | /__knowledge_settings__ and /__knowledge_restore__; existing retention settings and recovery responses |
| Import progress | /__knowledge_stream__, /__harvest_stream__; SSE JSON line/done events; /__knowledge_run__ for measured runtime state; POST /__knowledge_stop__ requests checkpoint-safe cancellation |
| Settings | /__model_settings__ reads/saves public configuration; /__model_test__ performs an explicitly requested connection test |
| Authentication | /auth/status, setup/login/logout/change; server-owned password/session state and localized error codes |
| Chat and staging | POST /chat and /__staging__/apply; existing conversation/review payloads |

No endpoint or payload shape changes in this refactor. Frontend scripted fixtures validate progress/chat behavior without launching imports or calling models; existing backend tests validate actual authorization and stop/recovery mechanics.

## Style cascade

dashboard.css owns compatibility layout and component geometry; visual-system.css owns the shared visual tokens, current light/dark surfaces and overview treatment. The visual-system stylesheet stays after the dashboard foundation, followed by component styles where currently assembled. Login uses its own small layout sheet plus the shared auth-card sheet. Extraction moves each existing rule exactly once and preserves cascade order. Legacy/pre-integration selectors remain where an older or standalone component still uses them; removing one requires browser equivalence evidence, not a filename-based assumption. Do not copy token overrides into another component sheet.

## Validation

A synthetic pre-refactor baseline checks exact rendered bytes for the dashboard and ten other page/component outputs. Architecture checks reject new large embedded UI blocks, and resource tests cover allowed names, single-pass values, cycles, manifest coverage and independent working directories. Wheel and actual browser checks cover installation, login/account, browsing, settings, chat, progress, both languages, responsive layouts, dark mode and reduced motion. The five frozen knowledge acceptance files remain unchanged.

After merging overlapping features, the active parity fixture records the explicit main snapshot at 5b4a97f, including global search, publication status and timelines. It was captured before resource extraction from an isolated Git archive with its source path asserted. The original pre-refactor fixture remains available; updated feature output is compared against the current main implementation rather than against obsolete pre-feature markup.
