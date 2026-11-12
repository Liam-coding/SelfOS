# Personal facts: missing records and abstraction (#9)

## Finding in the reported local snapshot

The zero count is consistent with the installed canonical data, not evidence that the source contains no personal facts. Read-only inspection found:

| Layer | Observation |
| --- | --- |
| Selected domains | Personal was enabled |
| Canonical snapshot | 57 old summaries; all lacked personal-fact/preference arrays; zero stored personal facts |
| Reusable staging checkpoints | 385 summaries with category fields; 216 personal-fact candidates |
| Latest staging snapshot | 97 retained personal facts; 115 archived personal records |
| Current status API | Zero canonical personal facts; needs_rebuild true; 385 saved checkpoints |

These are aggregate counts from one local installation, not targets or a population quality estimate. Candidate totals include inferred/historical records and can include repeated content. No private facts, raw review explanations, conversation files or credentials were copied into this report.

The newer extraction result has not replaced the older canonical snapshot. Source code in [knowledge.py](../src/selfos/app/knowledge.py) installs a rebuild only after consolidation and project refinement finish without cancellation/failure. A stopped or failed run preserves validated staging work and keeps canonical knowledge unchanged. get_status and knowledge_counts read the canonical snapshot. The stopped-run fixture in tests/test_personal_fact_snapshot.py reproduces zero visible facts with one retained staged fact, then resumes from the checkpoint with zero model calls and obtains one canonical fact. That fixture exercises the shared publication gate in incremental mode; the legacy-schema rebuild explanation relies on code inspection and the observed snapshot metadata.

This establishes why these displayed records are absent. It does not establish the precise final interruption cause of the user's run or prove that all staging candidates deserve retention. Old canonical fields alone do not prove an extraction bug: all 385 currently reusable staging summaries already contain the category fields. Reprocessing original conversations is not needed merely to explain the discrepancy.

## Trace through the current system

1. Source discovery/compaction retain user conversational text and distinguish assistant suggestions, quoted dialogue and runtime evidence. A small explicit self-report survives the synthetic import.
2. The model proposes typed records and evidence IDs. Personal records pass a semantic retention review. Technical/project choices should become project context, not personal attributes.
3. validate_record checks fields, source IDs and exact quotation; non-user sources downgrade a user_fact to inference. This is structural evidence validation, not semantic entailment.
4. merge_records honors domains, archives inferred/historical records, merges matching normalized key/value pairs, and flags contradictory personal values. It does not independently determine whether the quotation supports the claimed personal relation.
5. Transactional staging writes persist validated records and checkpoints. Successful installation publishes a coherent snapshot. The dashboard uses that installed snapshot.

Inference and historical routing explain some omissions legitimately. Explicit evidence can also be missed when a legacy record combines direct user evidence and assistant context in one source_ids list; the validator treats any non-user supporting source as sufficient to downgrade the whole claim.

## Independent boundary holdout

Run:

    python evals/run_personal_fact_holdout.py

The 17 anonymous cases are separate from the existing frozen evaluator/corpus. They cover durable self-reports, health conditions, assistant advice, quoted profiles, runtime output, project requests, dated measurements, historical roles, exclusions, invalid quotations and mixed supporting/context sources. This is a handcrafted adversarial boundary suite, not a blind or representative model benchmark.

The evaluator runs actual validate_record and merge_records against labeled candidate inputs. It does not call a model, simulate a successful review, or measure discovery/compaction/model extraction. Precision/recall below refer only to whether these supplied candidates become current personal facts at that boundary.

| Boundary metric | Result |
| --- | --- |
| True positives / false positives / false negatives | 6 / 4 / 1 |
| Precision | 60.0% |
| Recall | 85.7% |
| Structural source traceability among retained candidates | 100% |
| Model calls | 0 |

Four negative candidates remain current personal facts: a retry request miscast as an occupation, a project language choice miscast as an occupation, a dated temperature observation miscast as a durable current attribute, and a learning-format preference assigned to the wrong category. One explicit self-report is downgraded because assistant context was attached as additional supporting evidence.

These results show why exact citations cannot substitute for semantic support and why direct evidence needs a separate role from context. They are not measured end-to-end model precision/recall: production semantic review could reject the false positives. No numerical model-quality claim can be made from these tests; a later controlled model evaluation must use separately labeled source sessions and report temporary requests retained, eligible facts missed, and semantic/source support.

## Proposed abstraction rules and schema

Keep a fact when an explicit user statement supports an attribute, responsibility, life circumstance or interest of the person. Do not infer occupation, location, device ownership or language preference from project activity, file paths, tool output or language used. Assistant advice and imported AI profiles remain suggestions/inferences unless independently supported by the user's own statement.

Use stable relation keys such as employment.role, employment.responsibility, residence.city, education.status, interests.topic and health.condition. Normalize equivalent wording while preserving qualification and scope. The vocabulary describes relations rather than this user's personal rules; optional/custom relations and selected domains remain possible.

Each record should retain:

- Relation/key and structured value, plus concise display text.
- Subject and applicability scope: person, organization, location or a dated episode. A role in one team does not imply a global responsibility.
- Explicit/inferred attribution and category. Personal preferences remain preferences; project goals remain project context.
- Direct evidence references paired with their exact source spans. Supporting references must entail the claim; assistant/tool context belongs in separate context references and cannot upgrade certainty.
- Observed time and, when supported, valid_from/valid_to. Date a measurement as an observation/history instead of treating one reading as a permanent characteristic.
- Revision/conflict lineage and consolidation provenance. Equivalent statements merge support, not truth claims.

Examples:

| Input | Proposed output |
| --- | --- |
| I work as a product designer. | Explicit employment.role, with its supporting user span |
| I lead the accessibility team at Northwind. | Organization-scoped employment.responsibility; preserve organization context |
| Retry my API request. | Temporary/project request; no occupation inferred |
| My temperature was 38 C this morning. | Dated health observation in history; no permanent condition inferred |
| I was a teacher; I now work as a designer. | Old role in history, new explicitly revised role current, both sourced |
| I prefer diagrams for learning. | Learning-scoped preference, not a personal fact or global communication preference |
| An assistant suggests the user is a teacher. | Assistant suggestion/inference, not a verified personal attribute |

Consolidation must compare relation plus scope, not just similar text. If values differ and no explicit revision resolves them, retain a conflict instead of silently choosing the newest timestamp. A repeated statement does not become more certain merely through repetition. Detail controls expression, not truth or an arbitrary quota.

## Follow-up work

[#37](https://github.com/Liam-coding/SelfOS/issues/37) tracks the distinction between published knowledge and saved checkpoints, including category counts and clear resume/rebuild state, without installing incomplete snapshots. [#38](https://github.com/Liam-coding/SelfOS/issues/38) tracks semantic support/category validation, scoped relation keys and separate direct/context evidence. Evaluate the resulting behavior on independently labeled source sessions before claiming model-quality improvements. Preferences have their own investigation in #10.
