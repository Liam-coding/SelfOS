# Browser module interfaces (#49)

Status: proposed design; product implementation has not started. Base: main be271cc. The user authorized continuing the issue backlog and small reviewable PRs. The architecture below is a proposed implementation choice, not an already approved design.

## Intent and constraints

Make frontend ownership predictable after the resource extraction in #45 and shared styling in #48. Preserve the current UI, installed-package rendering, local authentication, knowledge evidence navigation, import stop/resume and locale runtime. Do not add a framework, bundler, ES-module requirement, generic string-evaluation action router, or a new backend job protocol. Do not store passwords/API keys/drafts persistently as part of this refactor.

## Approaches

1. Convert everything to ES modules. This improves lexical isolation but changes delivery, file/static access and script loading all at once. It is unnecessary for this issue's incremental acceptance.
2. Keep classic packaged scripts; introduce a small explicit lifecycle and narrow module interfaces, retain documented proxies while moving consumers. Recommended: fits existing generated/cached pages and can be reviewed in separate steps.
3. Only replace inline attributes with delegated handlers. This improves markup but leaves global state, startup requests and stream ownership implicit; it does not meet repeated-initialization acceptance.

Proceed with option 2 as the proposed technical choice. Full delivery is several small PRs; intermediate PRs must not close #49 while promised modules or acceptance remain incomplete.

## Current inventory (static source audit)

Nine templates contain 63 inline handler attributes: account-controls 4, dashboard-card 1, dashboard-page 16, import-controls 5, onboarding 14, overview 3, privacy 4, settings-model 15, workload 1. These counts include event attributes only, not dynamically assigned properties. Dynamic controls in knowledge browser/corrections, timeline, staging, quality and publication also assign onclick/onchange/onsubmit. Those assignments are legitimate node ownership but will move to explicit listener cleanup where nodes survive reinitialization.

Startup is distributed: settings, account, locale/theme, publication, knowledge browser, onboarding, quality and overview use DOMContentLoaded. Imports performs a recovery GET at script evaluation; chat/dimensions/staging attach immediately; workload owns a timer and three document subscriptions. The import controller is the only EventSource creator. Current cached refresh retires scripts via implementation text such as 'let isDark' and 'let knowledgeOperation'.

| Owner | Existing exposed/cross-module interface | Proposed interface/state |
|---|---|---|
| i18n | selfosI18n, selfos-language event | Keep existing runtime API; initialize translation once, no second locale store |
| account | fetch wrapper, authRequest/authStatus, logoutSelfOS, changeSelfOSPassword | account.request / logout / openChange; one auth-expiry wrapper per document |
| settings/model | openAppSettings, openModelSettings, saveModelSettings, model-list helpers | settings.open / openModel / saveModel; generations/draft/list requests private |
| theme | isDark, lang, toggleTheme/toggleLang/applyLanguage | theme.toggle / apply, locale change through i18n; no writable shared lexical variables |
| jobs | importRunning, confirmHarvest, recoverKnowledgeRun, stopKnowledge | jobs.start / recover / stop / snapshot / subscribe; one active stream or recovery poll |
| import settings | knowledgeOperation, openKnowledgeSettings, displayKnowledgeStatus, undoKnowledge | importSettings.open / save / restore; private operation ID and draft |
| publication/usage | renderImportPublication, refreshImportPublication, renderWorkloadUsage, saveWorkloadBudget | publication.render / refresh and usage.render / save; jobs subscriptions own polling |
| chat/dimensions | chatCollapsed/chatHistory, appendMsg/sendChat, _sendChatSilent, openDim/chatAboutDim | chat.open / toggle / send(text); dimensions.open / discuss uses chat interface |
| knowledge | browseKnowledge, openKnowledgeDetail, correction/timeline entry points | knowledge.browse / openDetail; corrections and timeline use explicit knowledge APIs |
| staging/overview | checkStaging/openStagingModal, updateKnowledgeOverview | staging.refresh / open and overview.refresh; subscribe to job completion |
| onboarding/privacy | openOnboarding and step/source/model helpers; privacy actions | onboarding.open / resume; privacy.open / save / export / import; model return hook explicit |

The implementation must produce a checked-in exact compatibility map from each remaining global to its template/script consumers. The table identifies current families, not permission to remove an unlisted helper without searching consumers. A global is retired only when no packaged or legacy-normalized consumer remains. Existing browser tests may call proxies until migrated to module APIs.

Preserve the existing read-only demo capability flag and correction editability checks; registration must not enable mutations in demo pages. Sparklines remains a stateless dashboard renderer with an explicit once-per-mounted-card initialization, rather than an implicit script-evaluation side effect. Compatibility also includes selfosCorrections.mount/history, projectTimelineLabel and the existing selfosReadOnlyDemo flag until their consumers migrate.

## Lifecycle and script delivery

Add a small versioned singleton at window.selfosUI with register(id, factory), init(document), module(id), and teardown() interfaces. Module factories close over state and are instantiated once per document/version. Re-evaluating a matching registration is a no-op; incompatible versions fail explicitly before mutating the mounted page. No dependency is installed.

Register all modules before a single bootstrap calls init: immediately when DOM is ready, otherwise through one once-only DOMContentLoaded handler. Dependencies are declared by module ID, topologically initialized, and missing/cyclic dependencies give a controlled error before module work. Locale and the auth request boundary precede dependent modules. The runtime itself performs no model calls, source scans or import starts.

Each migrated script is isolated in an IIFE; it must not retain global top-level let/const declarations that would fail before register on repeated delivery. Registration/factory construction is DOM- and I/O-free. init owns mounting and reads. Preflight the whole registered dependency graph before initialization, then keep a cleanup stack if mounting fails; cleanup cannot undo completed network reads, so no startup action may mutate server state. Login registers only its supported subset, whose dependencies must not require dashboard features. Compatibility proxies are installed once and resolve the current module API; repeated delivery must not overwrite state or stack wrappers.

Each module owns its persistent state, outstanding request generations, subscriptions and DOM bindings. Repeated init on the same document and same nodes is a no-op: it must not reset form values, list/search state, drafts, chat history or in-flight operations. Listeners are attached with module-owned AbortControllers (or a small cleanup list where necessary); readiness and document subscriptions are registered once. Newly inserted dynamic result nodes own their own listeners and become collectible when removed.

This iteration does not support arbitrary live replacement of feature DOM. If a caller replaces a module root while busy, the module reports a remount-required/busy condition rather than rebinding silently. A deliberate idle remount uses explicit unmount/mount with cleanup and an in-memory nonsecret state snapshot. Never serialize credential fields. Ordinary page navigation creates a fresh document; preserving drafts across navigation is a separate capability, not an invented promise of this refactor.

New HTML uses scoped data-selfos-action identifiers mapped to known callbacks by its owning module. No eval, Function, method-name lookup from arbitrary input, or inline code strings. Bind real submit/change/input/click semantics; handle nested target clicks via closest plus root containment; prevent duplicate chat-header toggles from button bubbling. Preserve keyboard and form validation behavior.

## Async ownership and import safety

The jobs snapshot includes kind ('knowledge' or 'harvest'), phase and active transport identity. Both kinds share the existing one-active-run mutex. Recovery and stop capability are keyed by kind, not inferred from a generic stream error. Chat request cancellation/generation handles are per request inside its module, not one AbortController that aborts a preceding explicit send; teardown cleans up all remaining client requests without replaying them.

jobs owns active EventSource, recovery timeout, run generation and running flag. init checks knowledge status once but never launches an import; reinit neither reconnects nor stops an existing run. start while active returns the existing state, not a second stream. Knowledge stream failure closes that stream before knowledge-status recovery polling starts. Legacy Harvest is a distinct kind: its stream error closes the connection and shows the existing connection-lost terminal state, without querying knowledge status or pretending it is resumable. Its success retains staging refresh; knowledge completion retains the knowledge finished event consumed by publication/usage. Finished/cancelled runs stop the applicable timers and emit one applicable terminal notification. stop remains the explicit knowledge-stop POST; it is not enabled for legacy Harvest. Auth expiry retains existing redirect/recovery semantics. UI teardown closes client transports and invalidates stale callbacks; it never silently POSTs stop or starts a replacement task. A new document recovers knowledge through status GET, matching current behavior.

usage subscribes once to job transitions and owns one refresh interval. publication, quality, overview, staging and onboarding each subscribe once; no automatic refresh should overwrite open dirty forms. Separate endpoints may still issue their own initial reads; the invariant is one read per owner per initialization, not a speculative backend-response cache. Concurrent refresh requests in a single owner coalesce or use existing generation checks. Close/reopen invalidates stale draft loads; older replies cannot overwrite current settings. Preserve explicit save/restore and completion refresh behavior.

Chat uses one private history owner and a common send helper for typed and dimension-triggered messages. Preserve existing overlap semantics: each explicit invocation appends its user message immediately and sends the then-current JSON history snapshot; independent successful replies append in completion order. Dimension-triggered requests may overlap typed requests. The shared helper does not introduce serialization, rejection of existing overlapping calls, or automatic retries. Typed sends retain input clearing and current button/focus behavior; dimension sends do not clear the draft. No history reset occurs during reinit. Binding must yield exactly one invocation per actual event; it must not create extra paid calls. Any new queue/deduplication or conversation-order policy is separate behavior work, not part of this refactor. Initialization never sends a chat message.

## Generated and cached pages

Package runtime and bootstrap resources in the existing manifest. Mark owned scripts with stable data-selfos-module IDs and a frontend generation marker. Current refresh replaces known owned script blocks by IDs; implementation-text markers remain only in a bounded legacy migration path for old generated pages, not the primary ownership rule. The legacy main combined script and known inline handlers are upgraded together. Exact allowlisted handler/element pairs become the new action markup; custom scripts and unrelated attributes are preserved. Never broadly execute or reinterpret custom handlers.

Refreshing server-side HTML is distinct from live init. It preserves score/history/user data and inserts one module generation. An old page upgraded repeatedly must contain one runtime, one script owner per feature and one bootstrap, with no old active counterpart. Standalone login loads the necessary subset; installed package resources must work outside repository cwd. The migration boundary must be explicit in tests, including pages from before #45 and current main.

## Delivery order and completion evidence

1. Inventory/compatibility map, lifecycle/runtime and bootstrap; migrate theme, settings/model and account first. Validate login/account and existing model-list race behavior without external calls.
2. Migrate jobs/import settings/usage/publication and completion subscribers, keeping checkpoint and recovery APIs unchanged. Verify one stream, one stop, one terminal event and no draft reset after repeated init.
3. Migrate chat/dimensions, knowledge/corrections/timeline, staging, overview, privacy and onboarding; retire consumed globals only after cross-module tests. Finish generated/cached migration and exact remaining compatibility documentation.

For each step: small reviewable PR, fresh applicable tests, independent review, no changed frozen acceptance bytes. Final acceptance includes synthetic browser request/stream counters after three init calls and repeated script delivery, dirty form/history preservation, locale/theme changes, nested click/submit validation, successful/failed/stopped/disconnected/recovered imports, auth expiry, source paging/corrections/timeline, stale response protection, installed-wheel and old/current cached pages. Verify no unintended /chat or model-test calls at initialization. All provider responses are loopback fixtures; no private vault/conversation scans. Include current styling/accessibility checks from #48. Full #49 closes only when these module and workflow requirements are proved.
