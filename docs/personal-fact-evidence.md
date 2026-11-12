# Personal facts: applicability and evidence

Session organization still makes one normal extraction call. The same response
includes fact claim_type, applicability scope and optional context_source_ids.
Only direct user statements can support an explicit fact. Assistant/tool context
remains navigable, but neither upgrades certainty nor downgrades independently
supported user evidence. Legacy missing scope stays unknown.

Relations use extensible stable keys, such as employment.role or health.allergy.
Consolidation matches relation plus scope, preserves each direct quotation and
timestamp, and keeps conflicting values and their sources. Simultaneous roles
in distinct contexts coexist. Explicitly historical and inferred claims remain
history. No personal source, record-count target or user-specific rule is used.

The local boundary rejects declared incompatible categories and catches narrow
prose patterns for requests, project choices, preferences, dated measurements,
negation and fictional profiles. Source-native value wording supplies a necessary
lexical anchor; abstracted text and English relation keys organize that value.
Unanchored translations/synonyms remain reviewable history. These guards are not
a general semantic entailment algorithm: overlapping words can still describe an
unsupported claim, unfamiliar phrasing can evade a guard, and scope meaning still
depends on model extraction. Explicit labels and exact quotations are not proof
of factual truth.

The unchanged 17 supplied-candidate cases measure this deterministic boundary,
not model quality. Separate synthetic original sessions and the bounded evaluator
introduced with #40 measure labeled extraction only when actual predictions are
supplied. A separately authorized live run is still pending; no model precision
improvement or semantic quality acceptance is claimed from mocked responses.

Browser source details and managed Markdown distinguish direct support from
context. Earlier records without explicit supporting IDs are not retroactively
assigned invented direct evidence. Durable user edits and suppression are #15.
