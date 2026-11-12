# Recoverable first-run onboarding

Implement #24 after merged #47 (main5a1f7d6). The user authorized sequential implementation. Keep English default with Chinese labels and preserve existing model settings and knowledge. No agent tests scan private sessions or call a paid model.

## User flow

1. Welcome: describe projects, personal facts, preferences, reusable experience and history, with sources/backups. A fresh profile offers Get started; existing profiles keep their current dashboard. Settings includes a way to reopen or resume the guide.
2. Sources: show availability of supported local Claude Code/Codex directories without reading conversation content. Allow explicitly selected/custom directories. Custom locations satisfy the issue's custom-location-or-upload fallback; generic file upload remains its separate requirement. Explain supported JSONL input and show actionable missing/invalid source errors.
3. Model/network: reuse current provider/proxy form and explicit connection test. Keep model credentials in existing model configuration, not onboarding state. The test button explains that it makes one configured-model request. A saved configuration is not assumed to work until tested, but users may skip and return later.
4. Privacy/sample preview: choose exclusions before any conversation read/model processing. Explain the exact selected conversation excerpts and context sent to the configured API. Preview is local only; show selected source/session/message counts, clipping and worst-case model-call budget. Only Start sample authorizes processing. No page-load, language switch, skip or resume of the guide starts a model task.
5. Results: use the existing knowledge browser and original-source links. Show saved checkpoints separately from published results; the user decides whether to process more. Expanding scope requires a separate explicit action and workload preview.

Skip and resume retain progress. Unsaved form input survives language switching. Errors are localized and keyboard-accessible. The guide can be dismissed during loading; stale responses cannot replace a newer step/profile.

## Durable boundaries

Store versioned progress separately in the vault (.knowledge_onboarding.json), containing step/status/selection and preview identity, never credentials. Store source selection/exclusions separately (.knowledge_sources.json), reused by ordinary imports as well as the sample. Absent source configuration keeps existing discovery behavior. Custom directories must also be registered for authenticated source viewing; settings cannot authorize arbitrary file paths outside chosen roots.

Use existing safe paths, locks and atomic writes. Existing settings/knowledge remain untouched until the user deliberately saves a setting or starts processing. Onboarding metadata is not evidence for personal facts or preferences.

## Bounded sample (builder choices)

The default sample is at most two compact session parts, at most twenty conversational messages per selected session and a shared maximum of twelve configured-model requests including retries/reviews. Show any excerpt/session truncation explicitly. A transport-level shared counter enforces the request limit across extraction, refinement and review; exhaustion preserves completed checkpoints and gives a recoverable result. This budget is specific to the sample, not the ordinary full importer.

Select source files before content reads. Directory enumeration is bounded (maximum 2000 candidate paths); read at most two selected files, each at most 8 MiB. Oversize files are reported and skipped rather than read in full. Symlinks leaving selected roots are skipped. The preview records selected file/message identities, hashes and the policy/source-selection hash. Starting/retrying revalidates the selected sources; changed files or settings require a new preview rather than silently sending additional content. Do not copy selected sources into fake conversation files or lose original provenance.

The existing import pipeline accepts a validated bounded message selection while preserving normal default behavior. The existing CLI, subprocess, SSE, stop file, canonical/staging separation, backups and publication are reused. Existing source-index fields remain authoritative. A sample preview identifier, not local paths or conversation text, goes in the stream URL. A running task can be stopped/resumed; resuming the guide itself never starts the task.

Sample publication is a scoped incremental merge, even when the existing global schema or policy is old. It must preserve unrelated canonical records and refine only projects touched by the sample. It must not publish a two-part replacement vault or falsely mark unprocessed legacy knowledge as globally upgraded. Normal later full rebuild behavior remains available; sample coverage metadata/fingerprints distinguish partial inputs from complete sessions.

Exclusions constrain both newly read sources and cached project/lesson/correction context sent to the model. Omit cached records with excluded or unclassifiable support from sample model context; mixed-support records are conservatively omitted if their text could include excluded material. Keep local historical knowledge intact rather than treating an exclusion as a deletion. The same persistent exclusion policy applies when a later normal import sends cached context.

The twelve-request budget is persisted per preview/sample operation and cumulatively consumed before each transport attempt, including failed requests, retries and internal review. Stop/restart/reload/resume do not reset it. Exhaustion stops further model calls and preserves checkpoints. Only a clearly labelled new sample allowance action creates a new budget after a fresh source/policy validation; retrying the same operation cannot mint another allowance silently.

Use explicit source selection/exclusion before processing more. Existing caches must distinguish clipped sample inputs from later complete-session inputs, so a larger import cannot accidentally treat unprocessed content as already covered.

Process more opens a new local workload preview with an explicitly larger bounded tier: at most four files, four compact parts and forty messages per selected session, with a new cumulative24-request allowance. The default remains2/2/20/12. Show the expanded numbers before the user starts; do not silently rerun the same cached sample or launch all history. Retrying/restarting either existing tier keeps its original cumulative budget.

## Validation

- Synthetic fixtures test empty/missing/custom sources, exclusions, bounded enumeration/content/model calls, source/hash changes, policy changes and cached-sample vs expanded-input identity.
- No model calls for read/skip/resume/preview; only an explicit connection test or sample start calls the configured transport.
- Fresh authenticated Chromium profile completes the flow using a loopback model fixture; source views work for custom roots, English/Chinese retain state, stop/reload/resume and skipped setup recover, and existing data/settings remain byte-identical until explicit mutation.
- Full pytest, installed-wheel foreign-cwd check and one independent whole-branch review before PR/merge.

## Review focus

Automatic initialization must not start imports. The model-call ceiling must count internal review/retry requests, not only pipeline tasks. Preview revalidation must not scan all historical content. Saved excerpts must not suppress later full-session work. Custom-root source viewing and persistent exclusions must use the same source selection as processing. Tests never use default home discovery.
