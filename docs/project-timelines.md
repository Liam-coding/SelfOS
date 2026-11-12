# Project timelines

Open a project in the knowledge browser and select **View project timeline**. The current project state stays above a chronological list of goals, decisions, progress and blockers. Filter milestone types, load more observations and read their recorded original conversations.

The view reuses the canonical project card, saved session summaries and existing state/decision lineage. It does not scan conversations, call a model, rewrite records or maintain another history database. It reloads canonical state on each API request, so a restore or saved edit affects the next view. Historical observations remain historical; changing the current goal does not establish that an earlier goal was explicitly superseded.

## Dates and evidence

- **Event time** is shown only when explicitly recorded.
- **Observation time** comes from recorded observation/session timestamps, not an inferred event date.
- **Source/session time** describes the registered supporting conversations.
- **Import time** is shown only when explicitly recorded. Existing summaries usually do not store it.

Chronology uses event time when available, then observation or source time. Entries state their ordering basis. Legacy project-context records have no reliable observation time and appear in a separate undated group. Equal-time observations remain visible; the view does not resolve disagreements by insertion order.

Project milestones are summary observations, not exact quotations or independently verified user claims. Source buttons reuse the existing registered-source reader and its allowed-root/message-identity checks. Missing metadata is counted explicitly. Unavailable, moved or changed originals produce localized feedback; paths and internal server errors are not rendered. Uploaded document support is part of #11 and #14; this PR does not add an upload producer or a new source adapter.

## API

Authenticated same-origin GET /__knowledge_timeline__ accepts an existing opaque project record id, category (all, goals, decisions, progress, blockers), nonnegative offset, and limit from 1 to 200. It returns the authoritative current summary, paginated milestones and registered source metadata. Unknown or changed project identities return 404; invalid filters/pagination return 400.

The new timeline UI uses packaged English and Chinese locales, English by default, DOM text rendering, responsive layouts, keyboard dialog controls and generation checks for delayed responses. Switching language retains the selected filter and already opened source text. Failed pagination can be retried at the same offset.

Responses include a projection revision. Send it with later pages; if canonical history changes between requests, the backend returns the first page with reset_required and a new revision. The UI replaces its old pages and announces the restart instead of silently repeating or skipping observations. Aggregate decision lineage contributes only source support not already covered by session observations; uncovered legacy decisions remain visible without invented dates.
