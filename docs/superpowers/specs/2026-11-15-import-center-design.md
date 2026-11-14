# Unified import center (#16)

SelfOS needs one place to inspect configured local conversation directories, native OpenCode databases and uploaded originals, then choose bounded organization. Reuse existing preview, privacy, job, publication and history services. No scan or model call occurs merely because the center opens.

## Design decision

Build a metadata read model and a private browser owner rather than another import engine. Show sources, local scan receipts, uploaded processing coverage, current job and durable operation outcomes together. Existing source setup and upload dialogs remain the editing/preview surfaces; the center links into them and the source-cited changes viewer. Opening an editor closes the center to avoid stacked modal dialogs.

## Behavior

- GET `/__import_center__` requires the existing local/auth/origin guards. It returns configured sources only, a paginated upload list, current job, publication metadata and a safe model label. No credentials or conversation bodies.
- Persist scan receipts after explicit local/native/upload previews: timestamp, bounded selected/pending parts, coverage, source identities and preview identity. Receipt counts describe that preview, never the entire conversation archive. Unscanned sources have unknown pending counts.
- Source selection/policy changes invalidate receipts. A scan receipt is provisional and is never evidence of canonical publication. Operation IDs and publication flags come from the existing canonical-aware publication service.
- Current running job is authoritative for stopping/recovery; center actions cannot initiate an unrestricted import. Bounded local/native/upload preview flows remain authoritative for admission and limits.
- Source rows show missing/excluded/ready or unscanned; uploaded rows reuse canonical receipt validation. Completed operations link to changes; interrupted/failed work offers existing checkpoint recovery.
- English default with complete Chinese catalog; responsive dialog, accessible status, keyboard close, text-safe rendering, request abortion and stale-response protection after close/remount, no duplicated handlers after cached refresh.
- Source status read failures are visible and isolated rather than silently deleting source rows. Upload pagination is bounded to 50. No personally identifying fixture inputs, paid model calls, new runtime dependency or price calculations.

## Verification

Synthetic tests cover read-only opening, receipt invalidation, unknown totals, canonical versus staged results, missing/corrupt metadata, authentication, pagination and privacy. Browser tests cover both languages, editor handoff, active-job stop/recovery, refresh/remount and hostile labels. Installed-wheel resource and cached-dashboard checks remain required.
