# Project knowledge acceptance contract

The user approved test-first work for code-discussion abstraction, transient-request filtering and project awareness. This round creates tests and a baseline only. Production code and personal vault data must remain unchanged.

## Behavior

- Keep why a change was needed, the chosen approach, outcomes, blockers and next steps; exclude bulk implementation bodies and repeated operational chatter.
- A transient command is not an enduring fact. Its useful result may be retained as context and verification evidence.
- Group by canonical project identity and original session identity. Never mix unrelated projects to fill character batches. Preserve chronological order and source identity.
- Each active project gets a current state card; reusable lessons are separately retained with sources. Newer status supersedes older status; past decisions remain available.
- Assistant reports of completion are not verified completion. Only explicit relevant verification evidence permits verified status. Unknown sources are rejected.
- Cache successful session summaries by content fingerprint. Restarting or replaying unchanged sessions makes no extra model calls. Failed sessions remain retryable.
- Bounded retries repair invalid model output; one failed session does not discard successful summaries of other sessions. Report incomplete coverage.
- Back up changes and preserve source links. Never overwrite unrelated personal files or write arbitrary model-selected paths.
- Compact representative bulk-code conversations by at least 70% without losing the issue, selected solution, result or source coverage. This is a synthetic acceptance threshold, not a promised real-world compression rate.

## Future API seam

Tests load knowledge_pipeline if present, otherwise the current knowledge module. Missing capabilities fail with an assertion rather than a collection/import error.

- compact_message(message: dict) -> dict | None: retain metadata, redact secrets, remove transient standalone chatter, compact code bodies; preserve explicit decisions/intents/blockers.
- prepare_sessions(messages: list[dict], max_chars: int = 12000) -> list[dict]: sessions contain session_id, project_id, messages and fingerprint; split large sessions without mixing identities and preserve all retained source IDs.
- merge_project_card(current: dict | None, update: dict) -> dict: card fields project_id, title, intent, status, decisions, blockers, next_steps, source_ids, updated_at, verified. Merge unique decisions/sources; newest explicit status/blockers/next steps win. Older updates cannot roll back current status.
- validate_summary(summary: dict, session: dict) -> dict: summary contains project and lessons. Enforce known sources and evidence; normalize unsupported assistant completion to reported_complete with verified=false.
- consolidate_sessions(vault: Path, sessions: list[dict], summarize: callable, max_workers: int = 3, max_attempts: int = 2) -> dict: write cards under 02_Work/projects/, lessons under 05_Life/lessons.md, persist a session cache, back up writes; return completed_sessions, failed_sessions, model_calls and missing_projects. Errors are isolated by session, successful summaries cached, retries bounded.
- audit_coverage(sessions: list[dict], cards: list[dict]) -> dict: return missing_projects and unresolved_sessions; identical folder basenames do not imply identical projects.

Message metadata: id, session_id, project_id, project, role, text, timestamp, source, path. Tool evidence may additionally contain verification={command, exit_code, relevant: bool}; unrelated tool chatter is not kept.

## Measurement

1. Existing regression tests stay separate from new capability acceptance tests. Missing APIs are capability-not-implemented failures, not proof of poor AI reasoning.
2. Fixed synthetic dialogues evaluate extraction using the current configured API. No personal conversations are sent. The same dialogues and rubric are reused after development.
3. Automatic dialogue checks use explicit concept alternatives, forbidden claims, source validation and size limits. They are a repeatable proxy for quality, not a comprehensive semantic judge.
4. Record exact case-set hashes, per-case failures, model settings, request count and elapsed time. Never change expected answers just to improve the score. Test corrections require a documented reason and re-baselining.
5. Frozen corpus is a development acceptance set, not an unseen generalization set. Post-development review should add a separately reported holdout sample rather than blend it into the baseline.
