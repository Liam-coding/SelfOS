"""Bounded, metadata-only retention diagnostics; never discover or read sources."""
import json
import os
import re
from pathlib import Path
from selfos.app.library import _state, _records, knowledge_counts
from selfos.app.import_status import OPERATION, CHECKPOINT, OUTCOMES, PHASES

MAX_BYTES = 32 * 1024 * 1024
MAX_FILES = 100
MAX_EXAMPLES = 30
KNOWN_REASONS = {'outside_selected_domains', 'temporary_request', 'project_choice',
    'preference_claim', 'dated_observation', 'uncertain_personal_claim',
    'nonliteral_personal_claim', 'negated_personal_claim', 'transient_content',
    'runtime_content', 'empty_content', 'tool_content'}


def quality_report(vault):
    vault = Path(vault).resolve()
    incomplete = False

    def read(path, max_bytes=MAX_BYTES):
        nonlocal incomplete
        if not path.resolve().is_relative_to(vault) or path.stat().st_size > max_bytes:
            incomplete = True
            return {}
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict): raise ValueError()
            return value
        except (OSError, ValueError):
            incomplete = True
            return {}

    def files(folder):
        nonlocal incomplete
        if not folder.exists() or not folder.resolve().is_relative_to(vault): return []
        result = []
        with os.scandir(folder) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_FILES:
                    incomplete = True
                    break
                if not entry.is_symlink(): result.append(Path(entry.path))
        return result

    path = vault / '.knowledge_pipeline.json'
    raw = read(path) if path.exists() else {}
    # _state applies the durable correction ledger, but only after size/containment checks.
    correction = vault / '.knowledge_corrections.json'
    correction_data = read(correction, 8 * 1024 * 1024) if correction.exists() else {}
    state = _state(vault) if raw and not incomplete else {}
    for field in ('sources', 'cards', 'quality_sessions', 'quality_refinements'):
        if not isinstance(state.get(field, {}), dict): raise ValueError('Invalid report metadata')
    if not isinstance(state.get('retention_audit', []), list): raise ValueError('Invalid report metadata')
    from selfos.sources.selection import load_sources, allowed_source
    selection = load_sources(vault, defaults=[]) if (vault / '.knowledge_sources.json').exists() else None
    sources = state.get('sources', {})
    def permitted(identity):
        source = sources.get(identity)
        return isinstance(identity, str) and len(identity) <= 200 and isinstance(source, dict) and (
            selection is None or bool(source.get('path')) and allowed_source(source['path'], selection))

    examples = []
    stages = {key: {'total': 0, 'unit': unit} for key, unit in (
        ('filtering', 'messages'), ('extraction', 'saved_session_parts'),
        ('validation', 'failed_attempts'), ('category_review', 'verdicts'),
        ('consolidation', 'verdicts'))}
    def example(stage, reason, ids, category='all', record_id=None, job_id=None, unavailable=False):
        if selection is not None and any(not permitted(identity) for identity in ids): return
        ids = [identity for identity in dict.fromkeys(ids) if isinstance(identity,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,200}',identity)
            and (permitted(identity) or unavailable and selection is None)][:8]
        if not ids or len(examples) >= MAX_EXAMPLES: return
        item = dict(stage=stage, reason=reason, source_ids=ids, category=category)
        if record_id: item['record_id'] = record_id
        if job_id: item['job_id'] = job_id
        if unavailable: item['source_available'] = False
        examples.append(item)

    audit = state.get('retention_audit', [])
    for entry in audit:
        stage = 'consolidation' if entry.get('stage') in (
            'cross_batch_method_merge', 'project_observation_merge', 'record_merge') else 'category_review'
        stages[stage]['total'] += 1
        category = entry.get('category', 'all')
        if category == 'project': category = 'projects'
        if category == 'lesson': category = 'lessons'
        if category not in ('projects','lessons','personal_facts','preferences','history'): category = 'all'
        reason = entry.get('reason')
        if reason not in KNOWN_REASONS:
            reason = ('consolidated' if entry.get('merge_applied') is True or entry.get('leader') and entry.get('leader') != entry.get('id')
                else 'merge_not_applied' if entry.get('merge_applied') is False else 'merge_standalone') if stage == 'consolidation' else {
                'retain': 'review_retained', 'project_history': 'review_history', 'discard': 'review_discarded',
                'observation': 'review_history', 'both': 'review_split'}.get(entry.get('action'), 'reviewed')
        example(stage, reason, entry.get('source_ids', []), category)

    suppressed = {}
    correction_categories = {action.get('id'):action.get('category') for action in correction_data.get('actions', [])
        if action.get('active',True) and action.get('action')=='delete'}
    for entry in state.get('correction_review', []):
        category = correction_categories.get(entry.get('action_id'))
        if category not in ('projects','lessons','personal_facts','preferences','history'):continue
        suppressed[category] = suppressed.get(category,0)+1
        stages['category_review']['total'] += 1
        example('category_review','user_suppressed',entry.get('original',{}).get('source_ids',[]),category)

    extraction = dict(state.get('quality_sessions', {}))
    for key, summary in state.get('summaries', {}).items():
        if key not in extraction and isinstance(summary,dict):
            ids = [identity for category in ('personal_facts','preferences','history','lessons')
                for record in summary.get(category,[]) for identity in record.get('source_ids',[])]
            if isinstance(summary.get('project'),dict):ids += summary['project'].get('source_ids',[])
            extraction[key] = {'source_ids':list(dict.fromkeys(ids)), 'categories':{
                category:len(summary.get(category,[])) for category in ('personal_facts','preferences')}}
    stages['extraction']['total'] = len(extraction)
    for entry in extraction.values():
        for category, count in entry.get('categories', {}).items():
            if category in ('personal_facts','preferences'):
                example('extraction', 'extracted' if count else 'no_candidate', entry.get('source_ids', []), category)
    for row, _, refs, _ in _records(state)[:5]:
        example('extraction', 'retained', [source['id'] for source in refs], row['category'], row['id'])

    jobs = []
    unresolved = (vault / '.knowledge_pending.json').exists()
    checkpoint_jobs = {}
    operations = []
    for operation in files(vault / '.knowledge_jobs' / 'operations'):
        if operation.suffix != '.json' or not OPERATION.fullmatch(operation.stem): continue
        value = read(operation, 128 * 1024)
        status = value.get('status')
        if status not in OUTCOMES or value.get('phase') not in PHASES: continue
        operations.append((operation, value))
    from selfos.app.import_status import publication_status
    from selfos.knowledge.settings import validate_settings, DEFAULT_SETTINGS
    settings_path = vault / '.knowledge_settings.json'
    settings = validate_settings(read(settings_path, 128 * 1024)) if settings_path.exists() else DEFAULT_SETTINGS
    publication = publication_status(vault, state, settings,
        operation_paths=[operation for operation, _ in operations], scan_orphans=False, metadata_reader=read
        ) if not path.exists() or raw and not incomplete else {'operations': []}
    retry_eligible = {item['id'] for item in publication['operations'] if item['resume_eligible']}
    published_checkpoints = {value.get('checkpoint') for operation, value in operations
        if operation.stem == state.get('last_operation', {}).get('id') or value.get('installed') is True}
    for operation, value in sorted(operations, key=lambda pair: pair[0].stem):
        status = value['status']
        published = operation.stem == state.get('last_operation', {}).get('id')
        checkpoint = value.get('checkpoint')
        valid_checkpoint = isinstance(checkpoint, str) and CHECKPOINT.fullmatch(checkpoint)
        if valid_checkpoint and (checkpoint not in checkpoint_jobs or published or
                checkpoint not in published_checkpoints):
            checkpoint_jobs[checkpoint] = operation.stem
        resolved = bool(valid_checkpoint and checkpoint in published_checkpoints)
        if published: status = 'completed'
        elif status == 'running':
            from selfos.storage.files import _pid_alive
            pid = value.get('owner_pid')
            if not isinstance(pid, int) or not _pid_alive(pid): status = 'interrupted'
        unresolved |= not published and not resolved and status in ('failed','stopped','interrupted','running')
        jobs.append(dict(id=operation.stem, status=status, phase=value['phase'], published=published,
                         retryable=not published and not resolved and operation.stem in retry_eligible))
        filtering = value.get('filtering')
        if published and isinstance(filtering, dict):
            stages['filtering'].update(total=filtering.get('filtered_messages', 0),
                input_messages=filtering.get('input_messages', 0), scope='published_operation')
            for entry in filtering.get('examples', [])[:10]:
                reason = entry.get('reason')
                example('filtering', reason if reason in KNOWN_REASONS else 'runtime_content',
                        entry.get('source_ids', []), job_id=operation.stem)

    # Existing diagnostic payloads are read only within fixed bounds; public data
    # contains no error prose or response fields, even after credential redaction.
    folders = [vault]
    folders.extend(vault / '.knowledge_rebuild' / checkpoint for checkpoint in checkpoint_jobs)
    diagnostic_files = 0
    for base in folders:
        for run in files(base / '.knowledge_errors'):
            if not run.is_dir(): continue
            for diagnostic in files(run):
                if diagnostic.suffix != '.json': continue
                if diagnostic_files >= MAX_FILES:
                    incomplete = True
                    break
                diagnostic_files += 1
                value = read(diagnostic, 128 * 1024)
                if not value: continue
                stages['validation']['total'] += 1
                ids = value.get('known_source_ids', [])
                checkpoint_published = base != vault and base.name in published_checkpoints
                recovered = bool(ids) and any((entry.get('run_id') == run.name or
                    checkpoint_published and entry.get('run_id')) and set(ids).issubset(entry.get('source_ids', []))
                    for entry in extraction.values()) and (base == vault or checkpoint_published)
                recovered |= bool(ids) and any(run.name in (entry.get('run_id'), entry.get('review_run_id'))
                    and set(ids).issubset(entry.get('source_ids', []))
                    for entry in state.get('quality_refinements', {}).values()) and (base == vault or checkpoint_published)
                # Legacy summaries do not prove a later attempt repaired this error.
                unresolved |= not recovered
                job = checkpoint_jobs.get(base.name) if base != vault else None
                text = value.get('error', '')
                text = text.casefold() if isinstance(text,str) else ''
                reason = 'processing_failed'
                if 'timeout' in text or 'timed out' in text: reason = 'request_timeout'
                elif 'evidence' in text or 'quotation' in text: reason = 'invalid_evidence'
                elif 'source' in text: reason = 'invalid_source'
                elif any(token in text for token in ('429','502','503','504','rate limit','connection')): reason = 'provider_unavailable'
                elif any(token in text for token in ('json','schema','format','truncated')): reason = 'invalid_format'
                example('validation', 'recovered_attempt' if recovered else reason, ids,
                        job_id=job, unavailable=not all(permitted(identity) for identity in ids))
    counts = knowledge_counts(state)
    categories = {}
    for category in ('personal_facts','preferences'):
        rejected = sum(entry.get('category') == category for entry in audit if
            entry.get('action') != 'retain' and entry.get('merge_applied') is not True)
        explanation = 'retained' if counts[category] else 'unresolved' if unresolved else 'user_suppressed' if suppressed.get(category) else 'reviewed_zero' if extraction else 'unknown'
        categories[category] = dict(count=counts[category], reviewed_session_parts=len(extraction),
                                    rejected_verdicts=rejected, explanation=explanation)
    jobs.sort(key=lambda item:item['id'],reverse=True)
    return dict(counts=counts, categories=categories, stages=stages, examples=examples,
                jobs=jobs[:20], incomplete=incomplete or len(jobs)>20, canonical=True,
                scoped=bool(state.get('sample_coverage')), eligible_absence_proven=False)
