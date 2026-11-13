"""Read-only publication status and best-effort, noncanonical run journals."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from selfos.knowledge.settings import policy_hash
from selfos.storage.files import _atomic_write, _pid_alive

OPERATION = re.compile(r'[0-9]{8}T[0-9]{6}-[a-f0-9]{12}')
CHECKPOINT = re.compile(r'[a-f0-9]{24}')
PHASES = {'scanning', 'extracting', 'refining', 'publishing'}
OUTCOMES = {'running', 'stopped', 'failed', 'completed', 'interrupted'}


def _contained(vault, path):
    return path.resolve().is_relative_to(vault.resolve())


class RunJournal:
    def __init__(self, vault, identity, mode, expected, policy):
        self.vault = Path(vault).resolve()
        self.path = self.vault / '.knowledge_jobs' / 'operations' / (identity + '.json')
        self.data = dict(id=identity, owner_pid=os.getpid(), mode=mode,
                         expected_hash=expected, policy_hash=policy,
                         started_at=datetime.now(timezone.utc).isoformat(),
                         phase='scanning', status='running', checkpoint=None)

    def update(self, **values):
        self.data.update(values, updated_at=datetime.now(timezone.utc).isoformat())
        try:
            if not _contained(self.vault, self.path):
                return False
            _atomic_write(self.path, json.dumps(self.data).encode('utf-8'))
            return True
        except (OSError, ValueError):
            # Observability must never change canonical transaction success.
            return False


def _read(vault, path):
    if not _contained(vault, path):
        raise ValueError('external status path')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('invalid status shape')
    return data


def _date(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        date = datetime.fromisoformat(value)
        return date.isoformat() if date.tzinfo is not None else None
    except ValueError:
        return None


def publication_status(vault, canonical, settings, *, operation_paths=None, scan_orphans=True, metadata_reader=None):
    from selfos.app.library import knowledge_counts
    vault = Path(vault).resolve()
    canonical_path = vault / '.knowledge_pipeline.json'
    expected = hashlib.sha256(canonical_path.read_bytes()).hexdigest() if canonical_path.exists() else 'absent'
    published = canonical.get('last_operation', {}).get('id') if isinstance(canonical.get('last_operation'), dict) else None
    operations, referenced, diagnostics = [], set(), 0
    read_metadata = metadata_reader or (lambda path: _read(vault, path))

    def staging(checkpoint):
        nonlocal diagnostics
        if not isinstance(checkpoint, str) or not CHECKPOINT.fullmatch(checkpoint):
            return None
        path = vault / '.knowledge_rebuild' / checkpoint / '.knowledge_pipeline.json'
        if not path.exists():
            return None
        try:
            state = read_metadata(path)
            for field in ('cache', 'summaries', 'cards', 'sources'):
                if not isinstance(state.get(field, {}), dict):
                    raise ValueError('invalid staging map')
            if any(not isinstance(card, dict) for card in state.get('cards', {}).values()):
                raise ValueError('invalid staging card')
            for card in state.get('cards', {}).values():
                for field in ('state_records', 'decision_records'):
                    records = card.get(field, [])
                    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
                        raise ValueError('invalid card lineage')
                for field in ('decisions', 'decision_history'):
                    if not isinstance(card.get(field, []), list) or any(not isinstance(value, str) for value in card.get(field, [])):
                        raise ValueError('invalid card decisions')
            for field in ('lessons', 'personal_facts', 'preferences', 'history', 'records_history', 'project_observations'):
                if not isinstance(state.get(field, []), list):
                    raise ValueError('invalid staging list')
                if any(not isinstance(record, dict) for record in state.get(field, [])):
                    raise ValueError('invalid staging record')
            knowledge_counts(state)
            return state
        except (OSError, ValueError, TypeError, AttributeError, KeyError, IndexError):
            diagnostics += 1
            return None

    paths = operation_paths if operation_paths is not None else (vault / '.knowledge_jobs' / 'operations').glob('*.json')
    for path in sorted(paths):
        try:
            item = read_metadata(path)
            if not OPERATION.fullmatch(path.stem) or item.get('id') != path.stem:
                raise ValueError('invalid operation')
            phase, outcome = item.get('phase'), item.get('status')
            if phase not in PHASES or outcome not in OUTCOMES:
                raise ValueError('invalid lifecycle')
            checkpoint = item.get('checkpoint')
            state = staging(checkpoint)
            if isinstance(checkpoint, str) and CHECKPOINT.fullmatch(checkpoint):
                referenced.add(checkpoint)
            installed = item['id'] == published
            if installed:
                outcome = 'completed'
            elif outcome == 'running':
                pid = item.get('owner_pid')
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                    outcome = 'running' if _pid_alive(pid) else 'interrupted'
                else:
                    outcome = 'unknown'
            policy_compatible = item.get('policy_hash') == policy_hash(settings)
            if state is not None:
                try:
                    policy_compatible = policy_compatible and bool(state.get('policy')) and policy_hash(state['policy']) == policy_hash(settings)
                except (ValueError, TypeError, AttributeError):
                    policy_compatible = False
            compatible = policy_compatible and item.get('expected_hash') == expected
            staged_operation = state.get('last_operation') if state else None
            snapshot_published = installed or (isinstance(staged_operation, dict) and
                                               published is not None and staged_operation.get('id') == published)
            operations.append(dict(id=item['id'], status=outcome, phase=phase,
                published=installed, compatible=compatible,
                was_published=installed or item.get('installed') is True,
                snapshot_operation=staged_operation.get('id') if isinstance(staged_operation, dict) and isinstance(staged_operation.get('id'), str) and OPERATION.fullmatch(staged_operation['id']) else None,
                staged_snapshot_published=snapshot_published,
                resume_eligible=compatible and state is not None and not snapshot_published and outcome in ('stopped', 'failed', 'interrupted'),
                policy_compatible=policy_compatible,
                staged_counts=knowledge_counts(state) if state else None,
                saved_sessions=len(state.get('cache', {})) if state else 0,
                updated_at=_date(item.get('updated_at'))))
        except (OSError, ValueError, TypeError, AttributeError):
            diagnostics += 1

    orphan_paths = (vault / '.knowledge_rebuild').glob('*/.knowledge_pipeline.json') if scan_orphans else []
    for path in sorted(orphan_paths):
        checkpoint = path.parent.name
        if checkpoint in referenced or not CHECKPOINT.fullmatch(checkpoint):
            continue
        state = staging(checkpoint)
        if state is None:
            continue
        try:
            policy_compatible = bool(state.get('policy')) and policy_hash(state['policy']) == policy_hash(settings)
            operations.append(dict(id=checkpoint, status='unknown', phase='unknown',
                published=False, compatible=None, policy_compatible=policy_compatible,
                was_published=False,
                snapshot_operation=state['last_operation'].get('id') if isinstance(state.get('last_operation'), dict) and isinstance(state['last_operation'].get('id'), str) and OPERATION.fullmatch(state['last_operation']['id']) else None,
                staged_snapshot_published=isinstance(state.get('last_operation'), dict) and published is not None and state['last_operation'].get('id') == published,
                resume_eligible=False,
                staged_counts=knowledge_counts(state), saved_sessions=len(state.get('cache', {})), updated_at=None))
        except (TypeError, ValueError, AttributeError):
            diagnostics += 1
    published_ids = {item['id'] for item in operations if item['was_published']}
    if published:
        published_ids.add(published)
    for item in operations:
        item['staged_snapshot_published'] = item['was_published'] or item.pop('snapshot_operation') in published_ids
        if item['staged_snapshot_published']:
            item['resume_eligible'] = False
        item['source_recheck_available'] = (not item['staged_snapshot_published'] and
            item['policy_compatible'] and item['saved_sessions'] > 0 and
            item['status'] in ('unknown', 'stopped', 'failed', 'interrupted'))
    operations.sort(key=lambda item: (item['updated_at'] or '', item['id']), reverse=True)
    return dict(published_operation=published, operations=operations, diagnostics=diagnostics,
                source_validation='on_resume', staging_is_provisional=True)
