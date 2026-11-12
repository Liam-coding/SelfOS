# Knowledge import and recovery

For a bounded initial preview with custom sources, exclusions and a cumulative request allowance, use the [first-run guide](first-run-onboarding.md). The ordinary import flow below remains available separately.

SelfOS turns local AI conversations into traceable personal knowledge. The dashboard screenshot uses synthetic example records; it contains no personal conversation content.

## Run locally

Use Python 3.10 or later and install `requirements.txt` for Argon2id password hashing. Install pytest separately to run tests. See [authentication](authentication.md) for login and local recovery.

```powershell
python -m selfos serve
# Open http://localhost:7070
python -m selfos knowledge --dry-run    # Scan/filter/compact; no model calls or knowledge writes
python -m selfos knowledge             # Incremental import
python -m selfos knowledge --workers 1  # Lower concurrent API demand
python -m selfos knowledge --rebuild    # Explicit rebuild under the current policy
python -m selfos knowledge --restore-last
python -m selfos knowledge --restore RUN_ID
```

Configure your model and proxy on the dashboard under **模型与网络**, or use ANTHROPIC_API_KEY and optional ANTHROPIC_BASE_URL in .env. See [model settings](model-settings.md) for available interfaces. The configured endpoint receives redacted input and relevant knowledge context. Redaction is a safeguard, not a guarantee that every sensitive detail is removed. Review the source material and choose an endpoint appropriate for it.

## What is retained

| View | Retention rule |
| --- | --- |
| Personal facts | Explicit supported statements about the person; conflicting facts are marked |
| Preferences | Enduring explicit choices; superseded choices move to history |
| Projects | Purpose, state, decisions, blockers and next steps |
| Reusable experience | Reasoning with applicability and limits; local measurements/configuration remain observations |
| History | Meaningful prior decisions, project states, outcomes and scoped observations |

Transient commands, acknowledgements and pure runtime scaffolding are filtered. Mixed messages keep their actual rationale, goals and failure evidence. Code and bulk JSON are compacted only in the model input. No source file is shortened or rewritten.

Statements, assistant suggestions and inferences keep distinct provenance. Quoted AI content cannot become a user-authored fact. Model-selected evidence IDs resolve to original source spans. Project completion reported by an assistant remains unverified unless relevant execution evidence supports it.

## Stop, retry and restore

Stop prevents new scheduling and allows active requests to finish saving. Current API calls may take up to their configured timeout; this is cooperative cancellation. Saved session parts and completed project synthesis are checkpointed in local staging. Stopping before installation leaves canonical knowledge unchanged. Stream disconnection also requests cooperative stopping. A refresh or disconnected page checks /__knowledge_run__ and follows the existing task while it saves/stops; it does not start another task or automatically process the remaining conversations. Click Build Knowledge again to resume remaining work.

Retry reuses valid successful checkpoints when input, policy and the canonical baseline still match. A changed input or policy can require work again. Failed extraction parts are not marked complete. An invalid model response may be regenerated with validation feedback; diagnostics are redacted and retained under the active vault's .knowledge_errors/ directory, including nested rebuild staging directories. A retry log is not proof of success: check the later saved/completed status. Repeated exhausted failures leave the prior canonical state intact.

Whole-operation installation creates a transaction backup under .knowledge_backups/. Undo validates affected files before restoring and rejects later edits. Restore newer operations before older ones. Hidden state, source indexes, jobs, staging checkpoints and backups are local and Git-ignored.

Keep hand-written notes outside selfos-managed sections. Project-card updates replace only their managed block; exact legacy generated content can be upgraded while retaining appended notes. Unrecognized legacy edits are preserved intact rather than removed automatically, so an edited old summary may remain beside the new managed summary. If a project is filtered out, its unmanaged notes remain even though its generated card leaves the knowledge index.

## Quality limits

Grouping preserves source unions and explicit domains; local observations retain scope, dates, numeric values and identifiers. Independent method review compares abstractions with their original candidate summaries. It is a model judgment, not an independent raw-source entailment proof.

Multi-project summaries may still omit context. Fixed-corpus checks use literal concept alternatives, so correct paraphrases may fail a check. Program regression tests, fixed-corpus model scores and independent holdouts measure different things; none guarantees that every personal conversation will be summarized completely.

## Technical retention details

### Configurable knowledge retention

The dashboard knowledge settings select domains and detail: concise, balanced,
detailed. Domain selection controls what enters the knowledge base. Detail
controls expression and the current decision view, never a target total count.

Personal facts and preferences live in vault/knowledge/personal_facts.md and
preferences.md; changes and historical evidence live in history.md. Project
cards and reusable lessons keep their existing locations. Current personal
records require quoted user evidence; suggestions become historical context.
Conflicting facts remain explicitly marked.

Run python -m selfos knowledge to import incrementally. A changed policy automatically
rebuilds; python -m selfos knowledge --rebuild explicitly rebuilds. Both use staging
and replace canonical knowledge only after successful completion. Retries reuse
completed checkpoints when input, policy and canonical state are unchanged.
Original conversations are never changed. Three workers handle summaries;
commits remain serialized.

Final project synthesis routes every candidate as a reusable method, project
observation, both, or transient content. Routing uses batches of at most 20;
format repairs retry only the affected batch and preserve redacted diagnostics.
Equivalent methods across routing batches are compared in bounded windows
(at most 80 methods and 48,000 method characters per request). Every candidate
pair receives a comparison; distinct or uncertain methods remain separate.
Canonical method text comes from a supplied method and sources are unioned;
there is no retained-count target. This grouping is within each project.
Large method pools require more comparisons. Reference validation is structural
evidence, not proof that every generated inference is semantically supported.

An independent method-support review compares generated abstractions with the
original candidates and pre-synthesis project context. Generated methods cannot
serve as their own evidence. Unsupported additions are corrected, or the original
basis returns to project observations when it supplies no transferable mechanism.
This review uses at most eight methods per request, keeps an audit and all cited
sources, and preserves inference/unverified labels. Identical corrected methods
coalesce within a domain. It is a model judgment against summaries, not independent
verification of the original conversation.

Project observations also consolidate redundant descriptions within a project.
They keep existing text, all source references and an audit of original scope
and source dates. Explicit event times, configurations and statuses cannot be
collapsed into another scope; canonical text must preserve numeric values,
including signs, versions and long identifiers. Distinct outcomes remain separate.

The frozen live evaluation can use knowledge_pipeline.api_summarizer(root),
which delegates to the actual prepared-session summarizer without reshaping its
answers. Keep program tests, fixed-corpus quality scores and read-only personal
samples separate when assessing results.

The dashboard queries /__knowledge_run__ after a stream disconnect and on reload
to attach to a live task. It blocks duplicate imports until the current child
has finished saving. Only successful completion displays 100%.

Run python -m selfos knowledge --restore-last or use the dashboard undo button to
restore the whole last operation. Undo validates all files first and refuses to
overwrite subsequent manual changes. Existing --restore RUN_ID remains usable
for older backups. Manual notes outside managed sections survive rebuilding.
Settings are vault-specific and stored in .knowledge_settings.json.

The publication status panel separates canonical category counts from saved
extraction checkpoints and provisional records in each staging snapshot. Saved
sessions are published only after consolidation and refinement succeed. Snapshots
can overlap, so their counts are never added together. The count of compatible
saved summaries is not a count of independently verified personal facts.

New imports persist small operation journals under
.knowledge_jobs/operations/*.json, independently of canonical transactions.
They record scanning, extraction, refinement and publication phases and terminal
outcomes. Old staging without a journal is explicitly unknown. A running journal
with a verified dead owner is interrupted; successful canonical publication takes
precedence over a stale journal. Unreadable status files produce a bounded
diagnostic without exposing source text. Journal failure does not invalidate a
successful knowledge transaction.

Status queries do not scan source conversations, call models or restart imports.
Resume import deliberately enters the existing incremental importer, which
revalidates original source IDs and content before reusing compatible summaries.
New or changed conversations can still require model calls. Different settings
or a changed canonical base are shown as incompatible with the old operation;
policy changes can be rebuilt explicitly. Original conversations, backups and
atomic publication guarantees remain in place.
