# Knowledge quality report

Open **Why knowledge was retained** on the authenticated dashboard. Refreshing reads saved metadata only; it never scans conversations or invokes a model.

Current record counts use the same corrected projection as the knowledge browser. Filtering totals describe the published operation's input messages. Extraction totals count saved session parts with outcome metadata (including legacy saved summaries). Category and consolidation totals count recorded verdicts, not unique source messages. Validation totals count failed attempts, including repaired attempts. These units and scopes differ; do not subtract them as a funnel.

Personal facts and Preferences explain retained records, recorded zero outcomes, unresolved work or missing evidence. A zero never proves no eligible content exists. Samples, old records without outcome metadata, incomplete reads and model omissions remain explicit limitations.

Examples use safe reason codes and local source identifiers. Source links use the existing authenticated source viewer and its exclusions. Failed staging can have source identifiers absent from published knowledge; these are labeled unavailable rather than linked to a broken viewer. Job links open import progress and existing retry controls. Staging records never increase current record totals.

Reports display at most 30 examples and 20 jobs; metadata enumeration caps each directory at 100 entries and reads at most 100 diagnostic files. Canonical metadata is capped at 32 MiB, correction metadata at 8 MiB, and individual journal/diagnostic reads at 128 KiB. Exceeded limits or malformed JSON mark results incomplete or return a generic unavailable response. Raw error prose, model responses, credentials and absolute filesystem paths never appear in the report.

Synthetic validation: pytest coverage includes filtering, invalid evidence and repair, misclassification, fact consolidation, failed staging, exact current and filtering counts, source exclusions, bounded reads, authentication and cached-dashboard refresh. The browser smoke uses the actual packaged report panel and authenticated API with synthetic source files, verifying English/Chinese switching and 1280/390-pixel layouts.
