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

## Remaining work

This implements the single-pass contract and the scope/conflict foundation for #40. Evidence-backed explicit validity intervals, integration with durable user corrections (#15), and a separate independently labeled source-session model evaluation remain follow-up work. Deterministic candidate/contract tests are not model precision or recall measurements.
