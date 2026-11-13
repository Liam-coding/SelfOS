"""Bounded read-only workload estimates and measured request status."""
import hashlib
import json
import math
import os
import re
from itertools import islice
from pathlib import Path

from selfos.app.budget import read_budget, model_identity
from selfos.storage.usage import RequestUsage, _read, _path
from selfos.storage.settings import load_settings
from selfos.knowledge.identity import digest
from selfos.knowledge.settings import limits, policy_hash, VERSION
from selfos.sources.selection import load_sources, select_files
from selfos.sources.conversations import extract_conversations
from selfos.sources.compaction import prepare_sessions

PREVIEW_METADATA_BYTES = 32 * 1024 * 1024


def _preview_saved(vault, settings):
    cached, bounded, consumed = {}, False, 0
    folder = _path(vault, '.knowledge_rebuild')
    if not folder.exists():
        return cached, bounded
    with os.scandir(folder) as entries:
        for index, entry in enumerate(entries):
            if index >= 100:
                bounded = True
                break
            if not re.fullmatch(r'(?:[a-f0-9]{24}|[a-f0-9]{64})', entry.name):
                continue
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
                path = _path(vault, '.knowledge_rebuild/' + entry.name + '/.knowledge_pipeline.json')
                if path.is_symlink() or not path.is_file():
                    continue
                remaining = PREVIEW_METADATA_BYTES - consumed
                if path.stat().st_size > remaining:
                    bounded = True
                    continue
                with path.open('rb') as stream:
                    raw = stream.read(remaining + 1)
                consumed += len(raw)
                if consumed > PREVIEW_METADATA_BYTES:
                    bounded = True
                    break
                state = json.loads(raw)
                if not isinstance(state, dict) or not state.get('policy'):
                    continue
                if policy_hash(state['policy']) != policy_hash(settings):
                    continue
                if not isinstance(state.get('cache'), dict) or not isinstance(state.get('summaries'), dict):
                    continue
                for key, fingerprint in state['cache'].items():
                    if isinstance(key, str) and isinstance(fingerprint, str) and isinstance(state['summaries'].get(key), dict):
                        cached[(key, fingerprint)] = True
            except (OSError, ValueError, TypeError, AttributeError):
                bounded = True
    return cached, bounded


def _identity(path):
    before = path.stat()
    if before.st_size > 8 * 1024 * 1024:
        raise ValueError('Preview file exceeds size limit')
    with path.open('rb') as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    after = path.stat()
    if len(data) != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Preview source changed; preview again')
    return after.st_size, after.st_mtime_ns, hashlib.sha256(data).hexdigest()


def workload_preview(vault, config_root):
    settings = load_settings(vault)
    selection = load_sources(vault)
    paths, warnings = select_files(selection, file_limit=8)
    identities = [_identity(path) for path in paths]
    messages = extract_conversations(paths)
    if identities != [_identity(path) for path in paths]:
        raise ValueError('Preview sources changed; preview again')
    state = _read(_path(vault, '.knowledge_pipeline.json'), {}, 32 * 1024 * 1024)
    if not isinstance(state, dict) or not isinstance(state.get('cache', {}), dict) or not isinstance(state.get('project_aliases', {}), dict):
        raise ValueError('Invalid knowledge state for preview')
    sessions = prepare_sessions(messages, max_chars=limits(settings)['session_chars'], aliases=state.get('project_aliases', {}))
    saved, checkpoint_limit = _preview_saved(vault, settings)
    if checkpoint_limit:
        warnings.append({'code': 'checkpoint_limit'})
    current_policy = policy_hash(settings)
    compatible = state.get('schema_version') == VERSION and state.get('policy_hash') == current_policy
    cached = 0
    for session in sessions:
        key = digest([session['project_id'], session['session_id'], session.get('part', 0)])
        fingerprint = hashlib.sha256((session['fingerprint'] + current_policy).encode()).hexdigest()
        if (compatible and state['cache'].get(key) == fingerprint) or (key, fingerprint) in saved:
            cached += 1
    pending = len(sessions) - cached
    projects = len({session['project_id'] for session in sessions})
    characters = sum(len(message['text']) for session in sessions for message in session['messages'])
    calls = {'low': pending, 'high': 6 * pending + 9 * projects}
    inputs = {'low': math.ceil(characters / 4) if pending else 0, 'high': characters + calls['high'] * 16000}
    outputs = {'low': 0, 'high': calls['high'] * 8192}
    budget = read_budget(vault, config_root)
    cost = ({edge: (inputs[edge] * budget['input_price'] + outputs[edge] * budget['output_price']) / 1000000
             for edge in ('low', 'high')} if budget['pricing_known'] else None)
    return {'files_scanned': len(paths), 'messages_scanned': len(messages), 'compact_parts': len(sessions),
        'pending_parts': pending, 'cached_parts': cached, 'projects': projects,
        'bounded': bool(warnings), 'warnings': sorted({item['code'] for item in warnings}),
        'budget': budget, 'estimate': {'calls': calls, 'input_tokens': inputs, 'output_tokens': outputs,
            'cost_usd': cost, 'assumptions': ['bounded_sources', 'character_heuristic', 'refinement_cache_unknown']}}


def usage_status(vault, config_root):
    budget = read_budget(vault, config_root)
    folder = _path(vault, '.knowledge_usage')
    candidates = list(islice(folder.glob('*.json'), 128))
    reports, diagnostics = [], 0
    try:
        candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    except OSError:
        diagnostics += 1
    for path in candidates[:20]:
        if not re.fullmatch('[a-f0-9]{32}', path.stem):
            continue
        try:
            meter = RequestUsage(vault, path.stem, budget['max_requests'])
            report = meter.status()
            cost_known = (budget['pricing_known'] and report['complete_usage'] and not report['cache_billing_unknown']
                          and report.get('model_identity') == model_identity(config_root) and not report.get('mixed_models'))
            report['cost_usd'] = ((report['input_tokens'] * budget['input_price'] + report['output_tokens'] * budget['output_price']) / 1000000
                                  if cost_known else None)
            reports.append(report)
        except (ValueError, OSError, RuntimeError):
            diagnostics += 1
    return {'budget': budget, 'runs': reports, 'diagnostics': diagnostics, 'bounded': len(candidates) >= 128}
