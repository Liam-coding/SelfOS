# Knowledge features and browser interfaces

This integration combines document upload, the pinned OpenCode adapter, source display, knowledge-change history and three-stage browser-interface work. It preserves both feature stacks without merging main or claiming arbitrary harness support.

## Preserved behavior

- Native database selection, added paths and project exclusions notify the source editor input boundary. The editor retains private dirty state and preserves drafts when metadata refreshes.
- Uploaded records retain their import-time label and admitted source-text start offset. Original bytes and permissions remain checked by the existing source APIs.
- Knowledge details retain record/category-scoped history navigation, correction drafts, timeline paging and source continuation. A delegated knowledge action opens the existing history interface; history is not added to model context.
- Privacy exports retain none/recent/all history choices and bounded operation counts. Preparation shows the actual range, bytes and omission before a separate download. Prepared snapshots and their preview survive safe remount or reopening; changing export options invalidates the snapshot. Interrupted preparation cannot become downloadable through a late response.
- Cached library refresh preserves adjacent custom scripts while replacing known search owners. Dashboard refresh keeps exactly one upload, change-history and lifecycle component. Queued close events cannot cancel a newly reopened dialog.

## Interface scope

The lifecycle inventory in browser-compatibility-map.json covers modules migrated under issue #49. Upload/native-source and change-history interfaces were delivered in parallel feature work and are retained by this integration. Their stable source-input and history entry points are intentional boundaries. The compatibility function downloadPrivacyData delegates to the privacy owner's prepared-download method.

## Validation boundaries

Integration checks use synthetic sources and loopback model fixtures. They do not scan personal conversations or call paid providers. Browser checks cover authenticated English/Chinese workflows, installed packages, repeated refresh/init, stop/resume, sources, correction drafts, history/restoration and audit export. Physical macOS validation and arbitrary OpenCode/DeepSeek releases remain distinct scopes.

Feature PRs remain separate review units. Integrate both stacks before treating the combined branch as the deployment tree; intermediate lifecycle PRs must not independently resolve #49.

## Decisions and their limits

- Audit receipts use event identity for their own state reference while the head binds the receipt hash. Canonical/head mismatch requires explicit baseline repair; migration preserves receipt bytes and conservatively rejects old full-backup restores when rebased paths/bytes change. The cost is explicit repair or restoration refusal rather than guessing history.
- Completion subscriptions migrate with their owners. Reverse settings/onboarding and publication/import actions run after initialization instead of adding cyclic dependencies. Deliberately partial pages cannot launch a missing dependent owner.
- Inert factories may exist before mounting; the complete graph is preflighted before init. Live root replacement requires safe teardown/init. Compatibility callbacks normally run after readiness.
- Cached source/history pages, dirty forms and nonsecret correction fields/retry identity survive explicit remount. Interrupted metadata reads resume once; jobs and mutations never replay. The cost is retained in-memory drafts and potentially stale cached text until refresh. Successful correction save/cancel consumes its draft once.
- Legacy upgrades require recognized implementation markers, while explicitly unknown script owners remain preserved. Unmarked custom scripts that imitate legacy implementations remain an ambiguous boundary; styling checks cover supported fixtures rather than arbitrary custom pages.
- Maintained tests are collected separately from retained browser/wheel artifacts. Installed-package checks assert their import path and invoke fixtures directly to avoid repository-path fallback. Physical platforms and real-provider quality are separate evidence scopes.
- The synthetic remount server has a larger connection queue so canceled reads and reconnecting owners can coexist. A real TCP burst reproduces the old limit; this changes the test transport rather than relaxing workflow assertions. Windows-locked temporary browser artifacts may be retained.
- This delivery keeps the native source-input and record-history interfaces while integrating the feature stacks. The unified PR provides one tested main-delivery tree; the focused PRs remain available for review. No main merge is performed here.
