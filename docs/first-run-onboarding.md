# First useful knowledge, with a bounded sample

After login, a fresh knowledge profile offers **Get started**. Existing profiles retain their dashboard and can use **Settings > Resume setup**. English is the default; Simplified Chinese is available in Settings. Closing the guide or changing language preserves unsaved source inputs within the page.

1. Read what SelfOS keeps: projects, personal facts, preferences, reusable lessons and history, with sources and backups.
2. Choose Claude Code/Codex conversation folders or custom folders containing their JSONL exports. Use one absolute directory per line. Set exclusions before previewing. **Next** saves edited source selections; **Save source selection** is also available.
3. Use the existing model/network form. **Save and test connection** makes one configured-model request containing synthetic test text. Opening, skipping, reopening and previewing this guide make no model requests.
4. Inspect a local preview, clipping warnings and remaining allowance, then explicitly choose **Start sample**.
5. Stop through the progress dialog, resume the same sample through the guide, and browse published knowledge with original sources. Saved checkpoints are recoverable progress, distinct from publication.

## Limits and recovery

| Operation | Files | File size | Messages per session | Compact parts | Total HTTP attempts |
| --- | --- | --- | --- | --- | --- |
| Default sample | 2 | 8 MiB each | 20 | 2 | 12 |
| Explicit Process more preview | 4 | 8 MiB each | 40 | 4 | 24 |

Enumeration considers at most 2,000 entries and selects the newest eligible files within that set. The preview reports large files, links/junctions, inaccessible folders and clipping. Original conversation bytes remain unchanged. These limits apply to samples; the ordinary organizer is separate.

**Process more** opens a larger local preview without starting it or launching all history. Each preview binds hashes/size/modification times, message and compact-part identities, source selection and retention policy. Start/resume revalidates only the recorded files; changes require a fresh preview. Partial inputs have distinct cache fingerprints from later complete inputs.

The allowance is persisted per preview and consumed before every HTTP attempt, including failures, retries and internal reviews. Stop, reload, reopen and resume do not replenish it. After exhaustion, return to the preview step and explicitly create another preview/allowance. Existing checkpoints remain recoverable.

## Privacy and existing knowledge

Source selection is reused by ordinary imports and authenticated source viewing. Exclusions filter both new reads and cached context sent to the model. Mixed or unknown support is omitted conservatively; local historical records remain stored. Excerpts stay local until sample start. Synthesis uses source-supported summaries and limited manual correction intent; nested original-record ancestry and local paths are excluded from the correction prompt.

Samples publish scoped incremental changes and refine only touched projects. Unrelated projects survive older schema/policy versions. Sample coverage does not claim a whole-vault upgrade. Normal rebuild and backup/restore remain separate capabilities.

Versioned local metadata is separate from canonical knowledge:

- .knowledge_sources.json: roots/exclusions, maximum 64 KiB.
- .knowledge_onboarding.json: step/status/current preview, no credentials.
- .knowledge_onboarding/previews/id.json: bounded local preview, maximum 2 MiB.
- .knowledge_onboarding/budgets/id.json: cumulative allowance with a separate OS lock for claims.

Secrets remain in existing model configuration. Corrupt or missing preview/allowance metadata fails closed, without default-folder fallback or quota reset. Existing knowledge backups, recovery and correction ledgers remain authoritative.

## Validation

Tests use temporary synthetic sources and loopback models. Real Chromium covers English/Chinese, custom sources/exclusions, local preview without model calls, failed/successful connection tests, publication/source links, stop/reload/resume without re-extracting the first saved session, skip/reopen and explicit larger previews. Windows Python 3.11 and Chromium were exercised locally; installed-wheel and final review results are recorded in the PR. These checks do not claim a real-model extraction-quality evaluation.

See [model settings](model-settings.md), [import recovery](knowledge-import.md) and [knowledge corrections](knowledge-corrections.md).
