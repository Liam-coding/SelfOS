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
                  selected_messages=None, selected_sessions=None, sample_id=None, upload_preview_id=None,
                  request_id=None, request_cap=None, native_preview_id=None):
    # The job lock is separate from the canonical and staging commit locks.
    # It serializes imports while allowing the UI to signal cancellation.
    with _locked(Path(vault).resolve() / '.knowledge_jobs'):
        return _run_knowledge(vault, roots=roots, summarize=summarize, refine=refine,
            rebuild=rebuild, cancel=cancel, progress=progress, max_workers=max_workers,
            selected_messages=selected_messages, selected_sessions=selected_sessions, sample_id=sample_id,
            upload_preview_id=upload_preview_id, request_id=request_id, request_cap=request_cap, native_preview_id=native_preview_id)


def _run_knowledge(vault, *, roots, summarize, refine, rebuild, cancel, progress, max_workers,
                   selected_messages=None, selected_sessions=None, sample_id=None, upload_preview_id=None,
                   request_id=None, request_cap=None, native_preview_id=None):
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
        scoped = sample_id is not None or selected_messages is not None or selected_sessions is not None or upload_preview_id is not None
        if scoped:
            mode = 'incremental'
        operation = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:12]
    result = {'mode': mode, 'installed': False, 'status': 'completed', 'model_calls': 0,
              'operation_id': None}
    from selfos.app.import_status import RunJournal
    journal = RunJournal(vault, operation, mode, expected, policy_hash(settings))
    journal.update()
    usage = None
    usage_used_at_start = 0
    real_transport = summarize is None and refine is None
    try:
        budget = None
        budget_used_at_start = 0
        from selfos.app.privacy import selection_hash, guard_request, permitted_source, request_scope
        from selfos.sources.selection import load_sources
        privacy_hash = selection_hash(vault)
        selection = load_sources(vault)
        include_native = (roots is None and sample_id is None and upload_preview_id is None
                          and selected_messages is None and selected_sessions is None
                          and (vault / '.knowledge_sources.json').exists())
        native_previews = []
        context_filter = None
        if scoped or (vault / '.knowledge_sources.json').exists():
            from selfos.sources.selection import load_sources, allowed_source
            from selfos.app.knowledge_context import filter_project_context
            selection = {**load_sources(vault), '_vault': str(vault)}
            context_filter = lambda payload, state: filter_project_context(payload, state, selection)
        if sample_id is not None:
            from selfos.app.onboarding import resolve_preview
            from selfos.storage.onboarding import SampleBudget
            preview = resolve_preview(vault, sample_id)
            selected_sessions = preview['sessions']
            budget = SampleBudget(vault, sample_id)
            budget_used_at_start = budget.status()['used']
        if upload_preview_id is not None:
            if sample_id is not None or selected_messages is not None or selected_sessions is not None:
                raise ValueError('Document preview cannot be mixed with another selection')
            from selfos.app.upload_preview import resolve_upload_preview
            upload_preview = resolve_upload_preview(vault, upload_preview_id)
            selected_sessions = upload_preview['sessions']
        if roots is None and (vault / '.knowledge_sources.json').exists() and selected_sessions is None:
            from selfos.sources.selection import load_sources, allowed_source
            selection = load_sources(vault)
            roots = [path for directory in selection['roots'] for path in Path(directory).rglob('*.jsonl')
                     if path.is_file() and allowed_source(path, selection)]
        if include_native:
            from selfos.app.harness_previews import prepare_native
            for entry in selection.get('entries', []):
                if entry['kind'] == 'opencode_database':
                    preview = prepare_native(vault, entry, cancel=cancel)
                    native_previews.append(preview)
                    progress('OpenCode: ' + str(len(preview['sessions'])) + ' selected parts; scan ' + preview['status'])
                    if preview['status'] not in ('complete', 'partial', 'bounded_read', 'stopped'):
                        raise ValueError('OpenCode scan cannot continue: ' + preview['status'])
        messages = (selected_messages if selected_messages is not None else
                    [m for s in selected_sessions for m in s['messages']] if selected_sessions is not None else
                    extract_conversations(local_roots() if roots is None else roots, cancel=cancel))
        if (vault / '.knowledge_sources.json').exists():
            messages = [m for m in messages if permitted_source(m, selection, vault)]
            if selected_sessions is not None:
                selected_sessions = [dict(s, messages=[m for m in s['messages'] if permitted_source(m, selection, vault)]) for s in selected_sessions]
                selected_sessions = [s for s in selected_sessions if s['messages']]
        filtering = {}
        if mode == 'rebuild' and include_native:
            from selfos.app.harness_previews import replay_native, _session
            native_messages = replay_native(vault, previous, selection,
                [m for p in native_previews for s in p['sessions'] for m in s['messages']])
            messages.extend(native_messages)
            native_sessions = [_session(s) for s in prepare_sessions(native_messages,
                max_chars=limits(settings)['session_chars'], cancel=cancel, aliases=previous.get('project_aliases', {}))]
        else:
            native_sessions = [copy.deepcopy(s) for preview in native_previews for s in preview['sessions']]
        sessions = copy.deepcopy(selected_sessions) if selected_sessions is not None else prepare_sessions(
            [m for m in messages if not (mode == 'rebuild' and include_native and m.get('source') == 'opencode')],
            max_chars=limits(settings)['session_chars'], cancel=cancel, aliases=previous.get('project_aliases', {}), audit=filtering)
        sessions.extend(native_sessions)
        for preview in native_previews:
            if mode != 'rebuild':
                messages.extend(message for session in preview['sessions'] for message in session['messages'])
        if not sessions and any(preview['pending'] for preview in native_previews):
            result.update(status='stopped', native_scan_pending=True)
            return result
        if filtering:
            journal.update(filtering=filtering)
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
            [(s['project_id'],s['session_id'],s['fingerprint']) for s in sessions], privacy_hash],sort_keys=True).encode()).hexdigest()
        from selfos.app.budget import read_budget, model_identity
        from selfos.storage.usage import RequestUsage
        allowance = read_budget(vault, vault.parent)
        request_limit = min(allowance['max_requests'], upload_preview['budget_limit']) if upload_preview_id else allowance['max_requests']
        if request_cap is not None:
            if type(request_cap) is not int or not 1 <= request_cap <= 10000:
                raise ValueError('Invalid bounded import request allowance')
            request_limit = min(request_limit, request_cap)
        usage = RequestUsage(vault, request_id or sample_id or upload_preview_id or checkpoint[:32], None if budget is not None else request_limit,
                             delegate=budget, model_identity=model_identity(vault.parent))
        usage_used_at_start = usage.status()['used']
        usage.timer(True)
        journal.update(usage_id=usage.identity)
        from selfos.storage.usage import request_usage_scope
        def scoped_callback(callback):
            def invoke(item):
                # Each worker establishes its own scope; prebuilt provider
                # callbacks share the same durable transport allowance.
                with request_usage_scope(usage):
                    return callback(item)
            return invoke
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
        # Repair missing upload metadata in staging before cached refinement
        # fingerprints are checked. Existing immutable identities cannot change.
        from selfos.sources.documents import source_metadata, document_source, document_text, DOCUMENT_FIELDS
        document_state = _state(scratch) or {'cache': {}, 'cards': {}, 'lessons': [], 'sources': {}}
        metadata_changed = False
        verified_documents = set()
        immutable_documents = {}
        from selfos.sources.adapters import verified_inputs
        verified_harness = {}
        def original_path(source):
            value = Path(source.get('path', '').replace(chr(92), '/'))
            return (value if value.is_absolute() else vault / value).resolve()
        for message in messages:
            known = document_state.get('sources', {}).get(message['id'])
            if message.get('source') == 'opencode':
                combined = {**message, **source_metadata(message, known)}
                verified = verified_inputs(vault, [combined], selection)[0]
                candidate = source_metadata(verified, known)
                candidate = source_metadata(verified_inputs(vault, [candidate], selection)[0])
                verified_harness[message['id']] = candidate
                if candidate != known:
                    document_state.setdefault('sources', {})[message['id']] = candidate
                    metadata_changed = True
                continue
            if message.get('source') != 'uploaded_file':
                if known and known.get('source') == 'uploaded_file':
                    raise ValueError('Uploaded source identity changed')
                continue
            incoming = source_metadata(message)
            candidate = dict(known) if known else incoming
            if known:
                known_identity = source_metadata(known)
                if (any(known_identity.get(key, '') != incoming.get(key, '') for key in ('source', 'role', 'provenance'))
                        or original_path(known) != original_path(incoming)):
                    raise ValueError('Uploaded source identity changed')
                for key in ('content_sha256', 'original_filename', *DOCUMENT_FIELDS):
                    if key in known and key in incoming and known[key] != incoming[key]:
                        raise ValueError('Uploaded source identity changed')
                    if key not in candidate and key in incoming:
                        candidate[key] = incoming[key]
            document_hash = candidate.get('content_sha256')
            verification = (str(original_path(candidate)), document_hash) if isinstance(document_hash, str) else None
            if verification is None or verification not in verified_documents:
                document_source(vault, candidate, limit=1)
                verified_documents.add(verification)
                immutable_documents[verification] = candidate
            if known and candidate != known:
                document_state['sources'][message['id']] = candidate
                metadata_changed = True
        if metadata_changed:
            _atomic_write(scratch / '.knowledge_pipeline.json', json.dumps(document_state, ensure_ascii=False, indent=2).encode())
        progress(f'Scanned {len(messages)} messages; compacted into {len(sessions)} session parts')
        if cancel():
            result['status'] = 'stopped'
            return result
        journal.update(phase='extracting')
        raw_summarize = summarize or api_summarizer(vault.parent, budget=usage)
        raw_refine = refine or api_refiner(vault.parent,cancel=cancel,budget=usage)
        enforce = (vault / '.knowledge_sources.json').exists()
        from selfos.storage.harness_scans import native_parts
        checks = list(native_previews)
        if native_preview_id is not None:
            from selfos.app.harness_previews import resolve_native
            checks.append(resolve_native(vault, native_preview_id))
        def check_native_snapshots():
            for preview in checks:
                native_parts(vault, preview['entry'], preview['part_ids'], max_chars=preview['part_chars'])
        def safe_summarize(item):
            check_native_snapshots()
            inputs = [{**m, **verified_harness[m['id']]} if m.get('source') == 'opencode' else m for m in item['messages']]
            item = {**item, 'messages': verified_inputs(vault, inputs, selection)}
            if not enforce: return raw_summarize(item)
            with request_scope(vault,privacy_hash,item['messages']): return raw_summarize(item)
        def safe_refine(payload):
            check_native_snapshots()
            inputs = [{**source, **source_metadata(source, verified_harness.get(source['id']))}
                      if source.get('source') == 'opencode' else source for source in payload['sources'].values()]
            verified = verified_inputs(vault, inputs, selection)
            payload = {**payload, 'sources': {identity:source for identity, source in zip(payload['sources'], verified)}}
            for source in verified:
                if source.get('source') == 'opencode':
                    verified_harness[source['id']] = source
            if not enforce: return raw_refine(payload)
            with request_scope(vault,privacy_hash,payload['sources'].values()): return raw_refine(payload)
        imported = consolidate_sessions(scratch, sessions, scoped_callback(safe_summarize),
            max_workers=max_workers, cancel=cancel, progress=progress, settings=settings,
            cached_summaries={} if rebuild else _saved_summaries(vault,settings,cancel), upgrade_history=not scoped)
        result.update(imported)
        if imported['failed_sessions'] or cancel():
            result['status'] = 'stopped' if cancel() else 'failed'
            if usage.status()['exhausted']:
                result.update(status='stopped', budget_exhausted=True)
                progress('Request allowance reached; saved work is retained. Raise the allowance explicitly to resume.')
            return result
        journal.update(phase='refining')
        refined = refine_projects(scratch, scoped_callback(safe_refine),
                                  cancel=cancel, progress=progress, project_ids=selected_projects,
                                  context_filter=context_filter, upgrade_history=not scoped)
        result['model_calls'] += refined.get('model_calls',refined['projects'])
        if cancel():
            result['status'] = 'stopped'
            return result
        staged_state_path = scratch / '.knowledge_pipeline.json'
        if upload_preview_id is not None:
            from selfos.storage.upload_receipts import add_receipts
            staged = _state(scratch)
            add_receipts(staged, sessions, policy_hash(settings), operation)
            _atomic_write(staged_state_path, json.dumps(staged, ensure_ascii=False, indent=2).encode())
        staged_hash = hashlib.sha256(staged_state_path.read_bytes()).hexdigest() if staged_state_path.exists() else 'absent'
        if mode == 'incremental' and not imported['run_id'] and not refined['run_id'] and staged_hash == expected:
            return result
        state = _state(scratch) or {'cards': {}, 'lessons': [], 'sources': {}, 'summaries': {}}
        # Keep references to filtered input, without storing its raw content.
        for message in messages:
            from selfos.sources.documents import source_metadata
            state.setdefault('sources', {}).setdefault(message['id'], source_metadata(message))
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
        check_native_snapshots()
        if selection_hash(vault) != privacy_hash: raise ValueError('Privacy rules changed; restart the import')
        # Canonical metadata must contain only the copies verified at publication,
        # including sources touched by cached refinement rather than new input.
        for source in immutable_documents.values():
            document_text(vault, source)
        for source in verified_inputs(vault, verified_harness.values(), selection):
            state.setdefault('sources', {})[source['id']] = source_metadata(source)
        from selfos.storage.upload_receipts import prune_unbound_receipts
        prune_unbound_receipts(state)
        _atomic_write(scratch / '.knowledge_pipeline.json', json.dumps(state, ensure_ascii=False, indent=2).encode())
        from selfos.storage.records import record_writes
        for name, content in record_writes(scratch, state).items():
            _atomic_write(safe_path(scratch, name), content)
        # Empty selected project domains must also clear previously managed lessons.
        if not (scratch / '05_Life/lessons.md').exists():
            _atomic_write(scratch / '05_Life/lessons.md', b'# Reusable lessons\n\n<!-- selfos-managed-lessons -->\n<!-- /selfos-managed-lessons -->\n')
        if selection_hash(vault) != privacy_hash: raise ValueError('Privacy rules changed; restart the import')
        journal.update(phase='publishing')
        install_rebuilt(vault, scratch, expected_hash=expected, run_id=operation,
                        expected_policy_hash=policy_hash(settings), selected_projects=selected_projects,
                        expected_privacy_hash=privacy_hash)
        result.update(installed=True, operation_id=operation)
        if native_previews:
            from selfos.storage.harness_scans import acknowledge_scan
            from selfos.knowledge.identity import digest
            for preview in native_previews:
                receipts = {}
                for part_id, session in zip(preview['part_ids'], preview['sessions']):
                    project = previous.get('project_aliases', {}).get(session['project_id'], session['project_id'])
                    receipts[part_id] = dict(cache_key=digest([project, session['session_id'], session['part']]),
                        policy_hash=policy_hash(settings), fingerprint=hashlib.sha256((session['fingerprint'] + policy_hash(settings)).encode()).hexdigest())
                if receipts:
                    try:
                        acknowledge_scan(vault, preview['entry'], list(receipts), max_chars=preview['part_chars'], canonical=receipts)
                    except (ValueError, OSError) as error:
                        result.update(native_acknowledgement_pending=True, native_acknowledgement_error=str(error))
                        progress('Knowledge saved; native checkpoint acknowledgement remains pending')
        return result
    except Exception as error:
        from selfos.sources.text import redact
        result.update(status='failed', error=redact(str(error)))
        if usage is not None and usage.status()['exhausted']:
            result.update(status='stopped', budget_exhausted=True)
        progress('Knowledge failed: ' + result['error'])
        return result
    except BaseException:
        result['status'] = 'interrupted'
        raise
    finally:
        if usage is not None:
            try:
                usage.timer(False)
                result['request_usage'] = usage.status()
                if real_transport or result['request_usage']['used'] > usage_used_at_start:
                    result['model_calls'] = max(0, result['request_usage']['used'] - usage_used_at_start)
            except (ValueError, OSError, RuntimeError):
                pass
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
