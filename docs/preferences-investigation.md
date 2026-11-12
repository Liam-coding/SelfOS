# Preferences: zero counts and contextual abstraction (#10)

## Why the reported category shows zero

The read-only snapshot audit shared with #9 found that personal was an enabled domain, but the installed canonical snapshot had no preference records and its 57 old summaries lacked preference arrays. The current status API therefore correctly returned zero. The newer, unpublished staging result contained 385 reusable summaries, 135 preference candidates, 82 retained preferences and 48 archived preference records.

The candidate labels were 84 user_fact and 51 inference. These are extraction labels, not independent judgments that the claims are true. All 135 summary candidates were marked current; later merging/routing can still archive records. Counts are observations from one local installation, not desired quotas or model-quality estimates.

The evidence establishes a published-snapshot discrepancy, not absence of extraction. A stopped/failed/unfinished run retains staging checkpoints but does not install a new canonical snapshot before successful consolidation and refinement. [The #9 report](https://github.com/Liam-coding/SelfOS/pull/39) includes a synthetic test of that shared publication boundary. The exact final interruption cause and validity of every saved preference remain unproven. No raw private sources or review explanations were included in this report.

## Preference-specific pipeline behavior

- Extraction requires an explicit enduring choice. The existing semantic-review prompt already says language use is not evidence of a language preference and a project constraint is not a global preference. Missing wording alone is not an established cause.
- Structural validation verifies exact quotes and known source IDs, and downgrades non-user supporting evidence. It does not establish that the quote states a preference, that its scope is correct, or that it lasts beyond the current task.
- Current merge logic requires a selected domain and user_fact attribution. Inferred/historical records go to history. Equivalent normalized key/value pairs merge support.
- Different values with the same normalized key are selected by latest observed_at. Scope is not included in matching, and equal-time contradictions have no explicit conflict policy. An observation timestamp alone does not prove that a preference supersedes a differently scoped one.
- The displayed count comes from canonical state. Semantic filtering, archival and transaction publication are separate causes of absent records and must be explained separately.

## Independent anonymous boundary evaluation

    python evals/run_preference_holdout.py

The fixture contains 16 labeled supplied candidates and five merge sequences, separate from the frozen evaluator/corpus. Predictions are produced by actual validate_record and merge_records; expected labels do not choose the returned verdict. No model, semantic reviewer or original conversation scan is invoked.

| Supplied-candidate metric | Result |
| --- | --- |
| True positives / false positives / false negatives | 5 / 5 / 0 |
| Precision | 50% |
| Recall | 100% of the five eligible supplied candidates |
| Retained-candidate structural source traceability | 100% |
| Model calls | 0 |

The five false positives are a today-only answer style, a one-off branch command, a project backend-language constraint, a Chinese-language message, and repeated Chinese-language messages. Each was supplied as a wrongly classified user_fact candidate; the structural boundary does not independently reject the semantic error. This does not establish that the production model/reviewer would emit or retain all these errors. A separate independently labeled source-session evaluation is needed for model precision/recall, including eligible preferences never proposed.

Three of five sequence scenarios passed: an explicitly revised choice, an older statement arriving after a newer one, and equivalent statements merging two source references. Two failed:

| Scenario | Expected | Actual boundary result |
| --- | --- | --- |
| Concise work updates and detailed research reviews | Both contextual preferences remain current | Research value replaces work value because matching ignores scope |
| Opposite values with identical timestamps and no revision evidence | Unresolved contradiction stays visible | One value wins by insertion order; the other is archived |

For the scope case, the evaluator supplies proposed scope metadata directly to the record boundary; the existing extraction wire schema does not expose that field. The case tests the current merge limitation if scope is available, not a claim that a model currently emits scoped records. These small adversarial cases are not a representative model benchmark and do not measure discovery or language-model extraction.

## Proposed abstraction and retention rules

Retain a preference when an explicit user statement describes an enduring or recurring choice in a stated context. A temporary action can be meaningful project history without becoming a personal preference. A contextual preference need not apply everywhere: detailed research reviews and concise work updates can both be valid.

| Input | Proposed abstraction |
| --- | --- |
| I prefer concise explanations in our conversations. | Explicit communication.detail; recurring conversation scope |
| For research reviews, I prefer detailed discussion. | Explicit communication.detail; research-review scope |
| Today, keep this answer short. | One-off task constraint, not an enduring preference |
| This repository should use Python. | Project decision, not a global programming preference |
| The user writes three messages in Chinese. | No explicit language preference established |
| From now on, use English for our conversations. | Explicit communication.language revision, sourced and dated |
| An AI suggests captions would help the user. | Assistant suggestion; no user preference inferred |

Default current preferences should be explicit only. Optional inferred tendencies must remain visibly labeled inference and outside explicit current preferences; repeated actions increase observation count, not attribution certainty. Do not add an approval requirement to the one-click import merely to promote guesses. A later voluntary explicit statement can establish a preference through new supporting evidence.

Proposed records contain stable relation/key and normalized value, subject, applicability scope, explicit/inferred kind, category/domain, direct supporting spans, separate context references, observed_at, supported validity/revision dates, and a conflict/supersession lineage. Preserve exact source links for every merged supporting statement. Relation vocabulary is configurable/extensible and not tied to this user's habits.

Consolidation compares relation plus scope. Equivalent choices merge evidence without broadening applicability. A different scoped value is not a revision. An explicit update within the same scope can supersede the old value while preserving history and its validity interval. Ambiguous/tied contradictions stay visible rather than being resolved by insertion order. Historical or withdrawn preferences should not be sent to an agent as current instructions.

## Next implementation work

[#37](https://github.com/Liam-coding/SelfOS/issues/37) covers published-versus-staged visibility. [#38](https://github.com/Liam-coding/SelfOS/issues/38) covers stronger evidence/category support shared with personal facts. [#40](https://github.com/Liam-coding/SelfOS/issues/40) tracks preference scope and revision/conflict behavior with an independent source-session holdout. Coordinate its persisted history with #17 and manual corrections with #15; preserve sources/backups and avoid an arbitrary retained-record count.
