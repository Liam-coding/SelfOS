# OpenCode ingestion

The reference adapter supports the session/message/part projection and info/messages exports in OpenCode v1.19.5, commit 810c0eba1a7348036f8bdf61e6632d0c36c6876c. Unknown or V2-only schemas are explicitly unsupported. DeepSeek Harness requires a separately identified distribution and format; this implementation leaves #12 open.

## Workflow and integrity

Choose an exact database in Settings → Resume setup → Choose local sources, save, and build a local preview. Discovery does not enable sources. Start explicitly processes at most two compact parts with twelve model requests, including retries/reviews. Stop retains checkpoints; the same preview retains its allowance. Next page prepares another bounded preview. New scan archives old progress and includes rows beyond the previous high-water mark.

Normalization filters ignored/synthetic/tool/reasoning/runtime content, applies existing redaction, and retains meaningful user/assistant text. The existing summarizer/refiner performs knowledge extraction: this adapter adds no second model classification stage. Native evidence keeps its existing content provenance; exports stay quoted evidence even for user-role records.

Logical IDs bind native project/session/message, directory, creation time, role, provenance and original meaningful-text digest. Physical paths are bounded copy locators, not logical identity. Project aliases change application grouping without rewriting evidence identity. Each model boundary, publication and source view checks permitted unchanged originals. Native requests also verify the consumed snapshot prefix, including records absent from the selected payload.

Read-only SQLite transactions see committed WAL data without altering upstream schema or checkpointing it. SelfOS publishes scan cursor, carry and sealed parts atomically in its own storage. Timestamp ties are buffered to preserve existing deterministic packing. Canonical cache receipts establish completion; checkpoint display alone does not. Restore requeues inputs whose receipts no longer match. An acknowledgement failure after installation reports saved knowledge with pending bookkeeping, preserving its operation ID.

Supported JSON exports pass strict bounded admission and preserve immutable raw bytes through the existing upload registry. Equivalent exports with different raw serialization can share logical evidence while keeping their separate document completion bindings. Migration validates source semantics against included immutable export bytes; foreign native permissions remain unresolved and are never automatically enabled.

## Limits and implementation decisions

| Decision | Reason and practical limit |
|---|---|
| Native databases require typed exact-file selection | Legacy directory permissions never silently authorize a database; existing users must explicitly enable it. |
| Unknown project directories are denied with explicit project exclusions | Opaque IDs cannot safely stand in for directory metadata; excluded unknown projects need better metadata or a deliberate rule change. |
| Relative OPENCODE_DB cannot escape the data root | An absolute override supports intentional external locations. |
| JSON and SQL creation times must agree | The pinned writer inserts SQL time from info.time.created and later updates data only; inconsistent records are diagnosed rather than rewritten. A broader profile needs separate validation. |
| Eight matching copy locators per logical source | Bounds evidence metadata; additional copies are not all retained. Native/export provenance remains separate. |
| Scan: 250ms busy timeout,10s deadline,100 sessions,2,000 messages,8MiB text | Partial/locked/oversize results are explicit; skipped records are diagnosed, not truncated. |
| Preview: two40-message pages and two sealed parts | A large timestamp tie may not seal within one preview. Continue locally; an oversized tie stops before cursor advancement. |
| Checkpoint8MiB, aggregate128MiB | Stricter than the64MiB snapshot allowance; crossing a cap preserves prior progress. Larger groups need a future bounded packing strategy. |
| Native rebuild replay2,000 logical messages/8MiB | Replays all retained permitted originals within the allowance; an oversized replay fails before replacement, preserving existing knowledge. |
| Parser in sources; immutable registry/index IO in storage | Keeps dependency boundaries acyclic. Preview construction and organization have separate application owners. |
| Added checkpoint history/receipts retain schema version1 | No OpenCode checkpoint format has shipped. Old development acknowledgements without receipts cannot reconstruct already discarded inputs. |
| Foreign paths are descriptive, not host IO targets | Portable metadata is validated with its origin platform. Users select local native locations after migration; included upload originals are rebased. |

Scan checkpoints and archives: vault/.knowledge_harness_scans/. Preview files: vault/.knowledge_harness/previews/. Upload originals and registry: vault/.knowledge_uploads/. Coordinate WAL when copying a live OpenCode database; copying its main file alone is not a coherent backup of live storage.

## Verification

Final complete regression: **1,311 passed,6 skipped**. A fresh whole-branch review found six Important issues; synthetic RED→GREEN regressions fixed native rebuild omission, production copy merging, aliases, consumed-prefix publication, post-install acknowledgement reporting and migration semantic forgery. Equivalent-export receipts and foreign-path IO boundaries have additional regressions. Frozen acceptance fixture bytes are unchanged.

Authenticated Chromium in English desktop/light and Chinese mobile/dark covers source selection, local preview without model calls, two-part native organization, stop before publication, same-preview resume, source navigation and JSON upload. Each locale uses five loopback fixture requests. These tests use synthetic data only; real-provider semantic quality, physical Mac compatibility and sudden power-loss guarantees are separate validation scopes.
