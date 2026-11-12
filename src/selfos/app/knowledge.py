"""app / knowledge responsibilities."""
import base64
import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from selfos.knowledge.settings import VERSION
from selfos.storage.settings import load_settings
from selfos.knowledge.settings import policy_hash
from selfos.storage.files import _locked
from selfos.storage.files import _atomic_write
from selfos.app.pipeline import consolidate_sessions
from selfos.sources.conversations import extract_conversations
from selfos.app.pipeline import install_rebuilt
from selfos.knowledge.settings import limits
from selfos.sources.conversations import local_roots
from selfos.sources.compaction import prepare_sessions
from selfos.storage.pipeline import recover
from selfos.app.pipeline import refine_projects
from selfos.storage.pipeline import safe_path

from selfos.app.knowledge_status import _state, _saved_summaries, get_status


def run_knowledge(vault, *, roots=None, summarize=None, refine=None, rebuild=False,
                  cancel=lambda: False, progress=lambda _: None, max_workers=3,
                  selected_messages=None, selected_sessions=None, sample_id=None):
    # The job lock is separate from the canonical and staging commit locks.
    # It serializes imports while allowing the UI to signal cancellation.
    with _locked(Path(vault).resolve() / '.knowledge_jobs'):
        return _run_knowledge(vault, roots=roots, summarize=summarize, refine=refine,
            rebuild=rebuild, cancel=cancel, progress=progress, max_workers=max_workers,
            selected_messages=selected_messages, selected_sessions=selected_sessions, sample_id=sample_id)


def _run_knowledge(vault, *, roots, summarize, refine, rebuild, cancel, progress, max_workers,
                   selected_messages=None, selected_sessions=None, sample_id=None):
    from selfos.providers.knowledge import api_summarizer, api_refiner
    vault = Path(vault).resolve()
    with _locked(vault):
        recover(vault)
        settings = load_settings(vault)
        previous = _state(vault)
        path = vault / '.knowledge_pipeline.json'
        expected = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else 'absent'
        mode = 'rebuild' if rebuild or (previous and (previous.get('schema_version') != VERSION or
            previous.get('policy_hash') != policy_hash(settings))) else 'incremental'
        scoped = sample_id is not None or selected_messages is not None or selected_sessions is not None
        if scoped:
            mode = 'incremental'
        operation = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:12]
    result = {'mode': mode, 'installed': False, 'status': 'completed', 'model_calls': 0,
              'operation_id': None}
    from selfos.app.import_status import RunJournal
    journal = RunJournal(vault, operation, mode, expected, policy_hash(settings))
    journal.update()
    try:
        budget = None
        budget_used_at_start = 0
        context_filter = None
        if scoped or (vault / '.knowledge_sources.json').exists():
            from selfos.sources.selection import load_sources, allowed_source
            from selfos.app.knowledge_context import filter_project_context
            selection = load_sources(vault)
            context_filter = lambda payload, state: filter_project_context(payload, state, selection)
        if sample_id is not None:
            from selfos.app.onboarding import resolve_preview
            from selfos.storage.onboarding import SampleBudget
            preview = resolve_preview(vault, sample_id)
            selected_sessions = preview['sessions']
            budget = SampleBudget(vault, sample_id)
            budget_used_at_start = budget.status()['used']
        if roots is None and (vault / '.knowledge_sources.json').exists() and selected_sessions is None:
            from selfos.sources.selection import load_sources, allowed_source
            selection = load_sources(vault)
            roots = [path for directory in selection['roots'] for path in Path(directory).rglob('*.jsonl')
                     if path.is_file() and allowed_source(path, selection)]
        messages = (selected_messages if selected_messages is not None else
                    [m for s in selected_sessions for m in s['messages']] if selected_sessions is not None else
                    extract_conversations(local_roots() if roots is None else roots, cancel=cancel))
        sessions = copy.deepcopy(selected_sessions) if selected_sessions is not None else prepare_sessions(
            messages, max_chars=limits(settings)['session_chars'], cancel=cancel, aliases=previous.get('project_aliases', {}))
        for session in sessions:
            session['project_id'] = previous.get('project_aliases', {}).get(session['project_id'], session['project_id'])
        selected_projects = {s['project_id'] for s in sessions} if scoped else None
        for session in sessions:
            if scoped and not session.get('partial_input'):
                from selfos.knowledge.identity import digest
                session['fingerprint'] = digest(['onboarding-partial-v1', session['fingerprint']])
                session['partial_input'] = True
            session['fingerprint'] = hashlib.sha256((session['fingerprint'] + policy_hash(settings)).encode()).hexdigest()
        checkpoint = hashlib.sha256(json.dumps([expected, policy_hash(settings), mode,
            [(s['project_id'],s['session_id'],s['fingerprint']) for s in sessions]],sort_keys=True).encode()).hexdigest()
        # Keep nested transaction paths within Windows' default path budget.
        scratch = vault / '.knowledge_rebuild' / checkpoint[:24]
        if not scratch.resolve().is_relative_to(vault):
            raise ValueError('staging escapes vault')
        scratch.mkdir(parents=True,exist_ok=True)
        from selfos.storage.corrections import load_corrections
        with _locked(vault):
            ledger=load_corrections(vault)
            _atomic_write(safe_path(scratch,'.knowledge_corrections.json'),json.dumps(ledger,ensure_ascii=False).encode())
        journal.update(checkpoint=scratch.name)
        if not (scratch / '.knowledge_pipeline.json').exists() and mode == 'incremental' and previous:
            with _locked(vault):
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError('Canonical import changed during scanning')
                names = ['.knowledge_pipeline.json', '05_Life/lessons.md',
                    'knowledge/personal_facts.md', 'knowledge/preferences.md', 'knowledge/history.md']
                names += ['02_Work/projects/' + hashlib.sha256(i.encode()).hexdigest() + '.md'
                          for i in previous.get('cards', {})]
                for name in names:
                    original = safe_path(vault, name)
                    if original.exists():
                        _atomic_write(safe_path(scratch, name), original.read_bytes())
        progress(f'Scanned {len(messages)} messages; compacted into {len(sessions)} session parts')
        if cancel():
            result['status'] = 'stopped'
            return result
        journal.update(phase='extracting')
        imported = consolidate_sessions(scratch, sessions, summarize or api_summarizer(vault.parent, budget=budget),
            max_workers=max_workers, cancel=cancel, progress=progress, settings=settings,
            cached_summaries={} if rebuild else _saved_summaries(vault,settings,cancel), upgrade_history=not scoped)
        result.update(imported)
        if imported['failed_sessions'] or cancel():
            result['status'] = 'stopped' if cancel() else 'failed'
            return result
        journal.update(phase='refining')
        refined = refine_projects(scratch, refine or api_refiner(vault.parent,cancel=cancel,budget=budget),
                                  cancel=cancel, progress=progress, project_ids=selected_projects,
                                  context_filter=context_filter, upgrade_history=not scoped)
        result['model_calls'] += refined.get('model_calls',refined['projects'])
        if cancel():
            result['status'] = 'stopped'
            return result
        staged_state_path = scratch / '.knowledge_pipeline.json'
        staged_hash = hashlib.sha256(staged_state_path.read_bytes()).hexdigest() if staged_state_path.exists() else 'absent'
        if mode == 'incremental' and not imported['run_id'] and not refined['run_id'] and staged_hash == expected:
            return result
        state = _state(scratch) or {'cards': {}, 'lessons': [], 'sources': {}, 'summaries': {}}
        state.update(schema_version=VERSION, policy_hash=policy_hash(settings), policy=settings,
                     quality_version=2, project_aliases=previous.get('project_aliases', {}))
        if scoped:
            if previous and (previous.get('schema_version') != VERSION or previous.get('policy_hash') != policy_hash(settings)
                             or previous.get('quality_version') != 2):
                for key in ('schema_version', 'policy_hash', 'policy', 'quality_version'):
                    if key in previous:
                        state[key] = copy.deepcopy(previous[key])
                    else:
                        state.pop(key, None)
            state.setdefault('sample_coverage', {})[sample_id or checkpoint[:24]] = {
                'projects': sorted(selected_projects), 'policy_hash': policy_hash(settings),
                'fingerprints': [s['fingerprint'] for s in sessions], 'quality_version': 2}
        state['last_operation'] = {'id': operation, 'action': mode, 'backup_run_ids': [operation]}
        _atomic_write(scratch / '.knowledge_pipeline.json', json.dumps(state, ensure_ascii=False, indent=2).encode())
        from selfos.storage.records import record_writes
        for name, content in record_writes(scratch, state).items():
            _atomic_write(safe_path(scratch, name), content)
        # Empty selected project domains must also clear previously managed lessons.
        if not (scratch / '05_Life/lessons.md').exists():
            _atomic_write(scratch / '05_Life/lessons.md', b'# Reusable lessons\n\n<!-- selfos-managed-lessons -->\n<!-- /selfos-managed-lessons -->\n')
        journal.update(phase='publishing')
        install_rebuilt(vault, scratch, expected_hash=expected, run_id=operation,
                        expected_policy_hash=policy_hash(settings), selected_projects=selected_projects)
        result.update(installed=True, operation_id=operation)
        return result
    except Exception as error:
        from selfos.sources.text import redact
        result.update(status='failed', error=redact(str(error)))
        progress('Knowledge failed: ' + result['error'])
        return result
    except BaseException:
        result['status'] = 'interrupted'
        raise
    finally:
        if budget is not None:
            try:
                result['request_budget'] = budget.status()
                result['model_calls'] = max(0, result['request_budget']['used'] - budget_used_at_start)
            except (ValueError, OSError):
                pass
        journal.update(status=result['status'], installed=result['installed'])


def restore_last(vault, operation_id=None):
    vault = Path(vault).resolve()
    with _locked(vault):
        recover(vault)
        operation = _state(vault).get('last_operation')
        if not operation or (operation_id is not None and operation_id != operation['id']):
            raise ValueError('operation changed or no operation to restore')
        simulated = {}
        folders = []
        for run in reversed(operation['backup_run_ids']):
            if not re.fullmatch(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{12}', run):
                raise ValueError('invalid backup id')
            folder = vault / '.knowledge_backups' / run
            if not folder.resolve().is_relative_to(vault) or (folder / 'restored').exists():
                raise ValueError('backup unavailable')
            manifests = sorted(folder.glob('*/pipeline-manifest.json'), reverse=True)
            if not manifests:
                raise ValueError('backup missing')
            folders.append(folder)
            for manifest in manifests:
                if (manifest.parent / 'rolled-back').exists():
                    continue
                for name, entry in json.loads(manifest.read_text(encoding='utf-8')).items():
                    path = safe_path(vault, name)
                    content = simulated[name] if name in simulated else (path.read_bytes() if path.exists() else None)
                    if (hashlib.sha256(content).hexdigest() if content is not None else None) != entry['after']:
                        raise ValueError('file changed after import: ' + name)
                    simulated[name] = base64.b64decode(entry['before']) if entry['before'] is not None else None
        originals = {n: base64.b64encode(safe_path(vault,n).read_bytes()).decode()
            if safe_path(vault,n).exists() else None for n in simulated}
        _atomic_write(vault / '.knowledge_pending.json', json.dumps(originals).encode())
        try:
            for name, content in simulated.items():
                path = safe_path(vault, name)
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, content)
        except BaseException:
            recover(vault)
            raise
        (vault / '.knowledge_pending.json').unlink()
        for folder in folders:
            _atomic_write(folder / 'restored', b'1')
        return {'restored': operation['id']}
