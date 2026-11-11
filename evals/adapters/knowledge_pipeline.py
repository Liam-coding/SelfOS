"""Evaluation-only compatibility for the byte-frozen evaluator and contract."""
from selfos.app.pipeline import SYNTHESIS_VERSION, _upgrade_cached_history, consolidate_sessions, install_rebuilt, refine_projects, register_project_aliases
from selfos.storage.documents import _project_unmanaged, render_card, render_project_document
from selfos.app.pipeline_api import api_summarizer
from selfos.knowledge.projects import audit_coverage, clean_actions, merge_project_card, validate_summary
from selfos.sources.compaction import canonical_project, prepare_sessions
from selfos.storage.pipeline import commit, recover, restore_pipeline_backup, safe_path
from selfos.knowledge.filtering import compact_message, content_identity, import_runtime_line, transient_only
from selfos.knowledge.identity import digest, unique
from selfos.sources.text import redact
