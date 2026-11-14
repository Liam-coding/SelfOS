"""Bounded questions over corrected, permitted retained knowledge."""
from pathlib import Path

from selfos.app.library import _state, _records
from selfos.app.privacy import model_state, selection_hash, request_scope
from selfos.sources.selection import load_sources
from selfos.knowledge.identity import digest
from selfos.knowledge.qa_retrieval import retrieve_records
from selfos.knowledge.qa_output import validate_answer


class KnowledgeQAError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _snapshot(vault):
    from selfos.storage.pipeline import safe_path
    for name in ('.knowledge_pipeline.json', '.knowledge_corrections.json'):
        path = safe_path(vault, name)
        if path.exists() and path.stat().st_size > 32 * 1024 * 1024:
            raise KnowledgeQAError('knowledge_too_large')
    policy = selection_hash(vault)
    try:
        state = _state(vault)
        rows = _records(model_state(state, load_sources(vault), vault))
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise KnowledgeQAError('knowledge_unavailable') from error
    if selection_hash(vault) != policy:
        raise KnowledgeQAError('knowledge_changed')
    return state, rows, policy, digest([state, rows, policy])


def question_context(vault):
    _, rows, _, _ = _snapshot(vault)
    projects = {}
    for row, _, _, _ in rows:
        for project in row.get('project_contexts', []):
            if len(project['id']) <= 100:
                projects[project['id']] = dict(id=project['id'], title=project.get('title', '')[:240])
    return dict(projects=sorted(projects.values(), key=lambda p: (p['title'], p['id']))[:200])


def _citation_revision(state, detail, sources, policy):
    return digest([detail, [state['sources'].get(source['id']) for source in sources], policy])


def _insufficient(locale):
    from selfos.web.i18n import translate
    reply = translate('qa.insufficient_reply', locale)
    return dict(status='insufficient_evidence', reply=reply, answer_kind='insufficient_evidence',
                references=[], inferences=[])


def answer_question(vault, config_root, question, project='', locale='en', answerer=None, cancel=lambda: False):
    vault = Path(vault).resolve()
    state, rows, policy, seal = _snapshot(vault)
    selected = retrieve_records(rows, question, project)
    selected_ids = {row['record']['id'] for row in selected}
    full = {row['id']: (detail, sources) for row, detail, sources, _ in rows if row['id'] in selected_ids}
    for row in selected:
        detail, original_sources = full[row['record']['id']]
        row['revision'] = _citation_revision(state, detail, original_sources, policy)
    def guard():
        if cancel():
            raise KnowledgeQAError('cancelled')
        try:
            current = _snapshot(vault)[3]
        except (ValueError, OSError, TypeError, KeyError) as error:
            raise KnowledgeQAError('knowledge_changed') from error
        if current != seal:
            raise KnowledgeQAError('knowledge_changed')
    guard()
    if not selected:
        return _insufficient(locale)
    sources = [state['sources'][source['id']] for _, original_sources in full.values() for source in original_sources]
    usage = None
    if answerer is None:
        import uuid
        from selfos.providers.knowledge_qa import answerer_for
        from selfos.storage.usage import RequestUsage
        usage = RequestUsage(vault, uuid.uuid4().hex, 2)
        answerer = answerer_for(config_root, locale)
    from contextlib import nullcontext
    from selfos.storage.usage import request_usage_scope
    feedback = None
    try:
        if usage:
            usage.timer(True)
        with request_usage_scope(usage) if usage else nullcontext():
            for attempt in range(2):
                guard()
                with request_scope(vault, policy, sources):
                    payload = answerer(question, selected, feedback=feedback)
                guard()
                try:
                    result = validate_answer(payload, selected)
                except ValueError as error:
                    feedback = str(error)
                    if attempt == 1:
                        raise KnowledgeQAError('invalid_answer') from error
                    continue
                if result['status'] == 'insufficient_evidence':
                    return _insufficient(locale)
                result['reply'] = result.pop('answer')
                return result
    finally:
        if usage:
            usage.timer(False)


def validate_citation(vault, record_id, revision, source_id=''):
    if not isinstance(record_id, str) or len(record_id) > 200 or not isinstance(revision, str) or len(revision) != 64:
        raise KnowledgeQAError('invalid_citation')
    state, rows, policy, _ = _snapshot(vault)
    for row, detail, sources, _ in rows:
        if (row['id'] == record_id and _citation_revision(state, detail, sources, policy) == revision
                and (not source_id or any(source['id'] == source_id for source in sources))):
            return dict(id=record_id, revision=revision)
    raise KnowledgeQAError('knowledge_changed')
