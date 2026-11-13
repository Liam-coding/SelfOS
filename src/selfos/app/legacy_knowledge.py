"""app / legacy_knowledge responsibilities."""
from selfos.app.diagnostics import _record_model_error
from selfos.app.diagnostics import _retryable_model_error
from selfos.knowledge.updates import _validate_updates
from selfos.sources.text import redact
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from selfos.knowledge.contracts import SOURCES
from selfos.knowledge.contracts import STATE
from selfos.knowledge.contracts import TARGETS
from selfos.storage.legacy import _commit
from selfos.sources.conversations import _hash
from selfos.storage.files import _locked
from selfos.storage.files import _read_json
from selfos.storage.legacy import _safe_path
from selfos.sources.conversations import build_batches

def _generate_validated(vault, run_id, batch_index, batch, context, generate, progress, max_attempts):
    feedback = ''
    for attempt in range(1, max_attempts + 1):
        response = None
        request_context = dict(context)
        if feedback:
            request_context['_validation_feedback'] = feedback
        try:
            response = generate(batch, request_context)
            return _validate_updates(response, batch)
        except Exception as error:
            feedback = redact(str(error))[:1200]
            progress(f'Batch {batch_index}, attempt {attempt}/{max_attempts}: {feedback}')
            try:
                diagnostic = _record_model_error(vault, run_id, batch_index, attempt, batch, response, error)
                progress(f'Diagnostic: vault/{diagnostic.as_posix()}')
            except Exception:
                progress('Could not save local diagnostic; original error retained.')
            if attempt == max_attempts or not _retryable_model_error(error):
                progress('Batch not saved; completed earlier batches are preserved. Retry remains available.')
                raise
            progress('Retrying generation with the validation error as repair feedback ...')


def import_knowledge(vault, messages, generate, progress=print, max_attempts=3):
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 5:
        raise ValueError('max_attempts must be an integer between 1 and 5')
    vault = Path(vault).resolve()
    from selfos.sources.selection import load_sources
    from selfos.app.privacy import selection_hash, guard_request, permitted_source, request_scope
    selection = load_sources(vault)
    expected_privacy = selection_hash(vault)
    config_path = vault / '.knowledge_sources.json'
    enforce = config_path.exists() and 'roots' in json.loads(config_path.read_text(encoding='utf-8'))
    if enforce:
        messages = [m for m in messages if permitted_source(m,selection,vault)]
        original_generate = generate
        def generate(batch, context):
            with request_scope(vault,expected_privacy,batch):
                return original_generate(batch, {} if selection['exclusions'] or selection.get('privacy_exclusions') else context)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:12]
    count, changed = 0, set()
    with _locked(vault):
        state = _read_json(_safe_path(vault, STATE), {'processed': [], 'facts': []})
        source_log = _read_json(_safe_path(vault, SOURCES), {})
        processed, known = set(state['processed']), set(state['facts'])
        batches = [[m for m in batch if m['fragment_id'] not in processed]
                   for batch in build_batches(messages)]
        batches = [batch for batch in batches if batch]
        progress(f'Knowledge: {len(messages)} messages, {len(batches)} new batches')
        for index, batch in enumerate(batches, 1):
            progress(f'Organizing batch {index}/{len(batches)} ...')
            context = {name: redact(_safe_path(vault, name).read_text(encoding='utf-8'))
                       for name in TARGETS if _safe_path(vault, name).exists()}
            # The saved vault is complete. Only context excerpts sent to the model are bounded.
            context = {name: text if len(text) <= 4000 else
                       text[:1900] + '\n[Existing knowledge excerpt: middle omitted]\n' + text[-1900:]
                       for name, text in context.items()}
            updates = _generate_validated(vault, run_id, index, batch, context, generate, progress, max_attempts)
            writes, batch_count = {}, 0
            for target, text, ids, kind in updates:
                fingerprint = _hash(target + ':' + re.sub(r'\s+', ' ', text).casefold())
                if fingerprint in known:
                    continue
                path = _safe_path(vault, target)
                original = writes.get(target, path.read_bytes() if path.exists() else f'# {Path(target).stem}\n'.encode())
                tag = {'user_fact': '[user-statement]', 'assistant_suggestion': '[assistant-suggestion]',
                       'inference': '[ai-inference]'}[kind]
                text = ' '.join(text.splitlines())
                details = '; '.join(f'{s} ({next(m for m in batch if m["id"] == s)["timestamp"]})' for s in ids)
                entry = f'\n- {tag} {text}\n  Source: {details}\n  Import: {run_id}\n'
                writes[target] = original.rstrip() + b'\n' + entry.encode('utf-8')
                known.add(fingerprint)
                batch_count += 1
                changed.add(target)
            for message in batch:
                processed.add(message['fragment_id'])
                source_log[message['id']] = {k: message[k] for k in ('source', 'path', 'timestamp', 'role', 'project')}
            writes[STATE] = json.dumps({'processed': sorted(processed), 'facts': sorted(known)}, ensure_ascii=False, indent=2).encode('utf-8')
            writes[SOURCES] = json.dumps(source_log, ensure_ascii=False, indent=2).encode('utf-8')
            _commit(vault, run_id, index, writes)
            count += batch_count
            progress(f'Saved batch {index}/{len(batches)}: {batch_count} facts; backup {run_id}')
    return {'facts': count, 'files': sorted(changed), 'run_id': run_id if batches else None, 'batches': len(batches)}
