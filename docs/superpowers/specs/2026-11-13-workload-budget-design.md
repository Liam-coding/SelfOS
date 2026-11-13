# Organization workload and request accounting (#22)

Users need to see eligible work before starting, control the number of requests, and distinguish measured usage from estimates. This implements the existing issue using the current Python pipeline and native internationalized UI. No background processing or full-history model evaluation is introduced.

## Product behavior

Import settings contains a local workload preview and budget controls. Preview scans at most 8 selected JSONL files, each at most 8 MiB, and enumerates at most 2000 directory entries. It is explicitly a bounded estimate, never a claim about all local history. It respects source exclusions, current compaction policy and exact reusable fingerprints; incomplete discovery is reported. Preview performs no model requests and creates no vault files.

Show scanned messages, compact parts, reusable/pending parts, affected projects, approximate token and request ranges. Token ranges use characters/4 through characters plus explicit request overhead assumptions; extraction, retries and project refinement make them estimates, not tokenizer results. Cached extraction does not imply project refinement is cached. Unknown pricing is unknown, never free.

Users can configure a cumulative request allowance (default 100, range 1..10000) and optional USD input/output prices per million tokens. Pricing is tied to the configured provider/model/endpoint; changing these makes prior pricing inapplicable until explicitly saved again. Limits apply to actual transport attempts, including errors and internal review calls. A stopped retry of the same work keeps its used allowance. Raising the allowance is explicit in settings. Onboarding retains its existing smaller cumulative allowance.

During processing, display transport attempts, failed attempts, reported input/output tokens, missing usage reports and elapsed time. Cost is approximate using the user-entered rates; incomplete usage or unsupported cache billing stays unknown. Existing stopped/failed jobs preserve checkpoints and backups. Exhaustion must not publish partial knowledge or silently send another request.

## Storage and boundaries

Budget settings live in vault/.knowledge_budget.json with no credentials. Per-work usage journals live in vault/.knowledge_usage/<work-hash>.json. Reads are bounded and contained; OS locks serialize concurrent workers and release on process exit. A transport attempt is charged durably before HTTP; failed and pending attempts still count. Observations are idempotent and preserve no prompts, credentials or raw provider responses.

The journal is observability, not canonical knowledge or a transaction backup. The preview and usage views do not mutate canonical state. Existing CLI, authentication, proxy handling, source checks and packaging continue to work. Python 3.10+, English default and Chinese translations are required.

## Verification

Small synthetic sources and a local recording HTTP server prove cache accounting, exclusions, bounded previews, concurrency, failed attempts, restart persistence and limit enforcement. Test malformed/missing usage, stale model pricing, changed configuration, budget exhaustion and stop/resume. Browser tests cover language switches, unsaved controls and useful progress without a paid provider or private conversation scan.
