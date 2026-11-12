"""Conservatively reconstruct model context from allowed-source summaries."""
import copy

from selfos.knowledge.projects import merge_project_card
from selfos.knowledge.settings import limits
from selfos.sources.selection import allowed_source


def filter_project_context(payload, state, selection):
    project_id = payload['project']['project_id']
    permitted = {identity for identity, source in state.get('sources', {}).items()
                 if source.get('path') and allowed_source(source['path'], selection)}
    def supported(record):
        ids = record.get('source_ids', []) if isinstance(record, dict) else []
        return bool(ids) and all(identity in permitted for identity in ids)
    summaries = []
    for summary in state.get('summaries', {}).values():
        project = summary.get('project')
        if (project and state.get('project_aliases', {}).get(project['project_id'], project['project_id']) == project_id
                and supported(project)):
            summaries.append({**copy.deepcopy(project), 'project_id': project_id})
    if not summaries:
        return None
    current = None
    for project in summaries:
        current = merge_project_card(current, project, limit=limits(payload.get('policy'))['decisions'])
    result = {**copy.deepcopy(payload), 'project': current,
              'lessons': [copy.deepcopy(record) for record in payload.get('lessons', []) if supported(record)],
              'intent_history': [{'title': project['title'], 'intent': project['intent']} for project in summaries]}
    ids = set(current['source_ids']) | {identity for record in result['lessons'] for identity in record['source_ids']}
    result['sources'] = {identity: copy.deepcopy(state['sources'][identity]) for identity in ids}
    if 'user_corrections' in result:
        corrections = result['user_corrections']
        project = corrections.get('project')
        corrections['project'] = {key: copy.deepcopy(project[key]) for key in ('title', 'intent', 'source_ids')
                                  if key in project} if supported(project) else None
        corrections['lessons'] = [{key: copy.deepcopy(record[key]) for key in ('text', 'source_ids', 'kind', 'domain') if key in record}
                                  for record in corrections.get('lessons', []) if supported(record)]
    return result
