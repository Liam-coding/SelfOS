# Single-pass preference extraction

Normal conversation organization sends each new or changed compact session part to the model once. The same structured response contains project context, lessons, personal facts, preferences and history. Preferences do not trigger a second extraction or automatic retention review. Invalid outputs can still require a repair retry. Project refinement is a separate operation and retains its existing review behavior.

The model identifies meaning, durable versus temporary intent, stable relation keys and applicability. Local code resolves exact evidence IDs, validates source attribution and scope, then merges and persists the result. Source validity does not prove semantic correctness; model extraction quality requires a separate source-session evaluation.

## Applicability

Preference scope is an object with type and id in the strict extraction schema:

- global: explicitly general applicability; empty id.
- activity: recurring context such as work-email or learning; stable descriptive id.
- project: current-project, resolved locally to the source session identity.
- unknown: evidence does not establish applicability; empty id.

Legacy records without scope remain readable as unknown. They are never silently promoted to global preferences. Project design decisions belong in project context; one-off commands should be omitted from personal preferences. These semantic decisions happen in the same model response, not a second model pass.

## Consolidation and history

Merge by relation plus scope. Equivalent values accumulate exact supporting quotations, source references and original message timestamps without broadening applicability. Different scopes coexist. Definitely newer supported statements may supersede older values; old values remain in history with source-linked supersession. Equal, missing or ambiguous observation times retain unresolved contradictions instead of choosing by arrival order. This does not infer an exact validity interval.

The browser shows applicability and unknown-scope warnings in English and Chinese. Managed Markdown retains scope and conflict/supersession sources, while preserving text outside managed sections. Existing checkpoint, cooperative stop/resume and backup handling remain in use.

For explicit diagnostic review, Python callers can still request api_summarizer(root, review_records=True). This adds a model call and is not the normal import default.

## Explicit changes and validity

The same extraction response can include a nullable revision object naming the previous value, effective date and an evidence ID. Local validation requires a direct user quotation supporting both values and an explicit change. A literal date must appear in that quotation; source-time is resolved from the original message timestamp only for an explicit now change. Unsupported dates, quoted AI, negated changes and invented manual-correction metadata are rejected.

An explicit source-backed revision can establish valid_from for the new choice and an exclusive valid_until boundary for the displaced choice. Ordinary observation-based supersession never invents an exact effective date. Validity evidence and source links remain available in details and history. Missing or ambiguous chronology stays conservative rather than fabricating a clock.

Date-only validity uses a UTC calendar-day boundary; original date text is retained. Future changes remain planned history and do not replace active preferences until their boundary is reached. Read snapshots activate due changes locally without a model call, and managed Markdown is updated on the next normal write. Browser cache signatures include the UTC minute so a new read cannot indefinitely reuse a pre-boundary snapshot. Repeated statements preserve the earliest supported start of a continuous stage. Conflicting effective dates remain flagged; no interval ending before its start is published.

Local manual-correction metadata is preserved during merge/replay. Different new evidence remains a visible conflict instead of silently replacing the correction. Models cannot create this metadata. The authenticated correction service and browser edit/delete/merge/undo controls are tracked separately in #15.

## Separate source-session evaluation

The synthetic sessions in evals/source_session_holdout.json are distinct from supplied-candidate merge tests. Their explicit category/relation/value/scope labels can be compared against supplied prediction files with evals/run_source_session_holdout.py. The report separates labeled extraction matches, temporary-request false positives and structurally valid retained records. Strict label matching is not a general semantic entailment proof.

Offline example: python evals/run_source_session_holdout.py --predictions predictions.json --output report.json. Supplying a model configuration root additionally requires --allow-model-calls and performs at most one extraction call per fixture session. No live-model evaluation has been performed as part of implementation; mocked or supplied outputs are not reported as measured model improvements.
