"""Stable streaming compaction; a timestamp tie is closed only by later input or session end."""
import copy
import json

from selfos.sources.compaction import canonical_project, pack_records, part_fingerprint
from selfos.knowledge.filtering import compact_message
from selfos.knowledge.identity import digest

MAX_CARRY_BYTES = 8 * 1024 * 1024


def _validate(carry, max_chars):
    keys = {'version', 'max_chars', 'project_id', 'session_id', 'next_part', 'part', 'deferred', 'timestamp'}
    if (not isinstance(carry, dict) or set(carry) != keys or carry['version'] != 1
            or carry['max_chars'] != max_chars or type(carry['next_part']) is not int
            or carry['next_part'] < 0 or not isinstance(carry['part'], list)
            or not isinstance(carry['deferred'], list) or not isinstance(carry['timestamp'], str)
            or not isinstance(carry['project_id'], str) or not isinstance(carry['session_id'], str)):
        raise ValueError('Invalid resumable compaction checkpoint')
    for message in [*carry['part'], *carry['deferred']]:
        if (not isinstance(message, dict) or not isinstance(message.get('text'), str)
                or not message['text'] or not isinstance(message.get('id'), str)
                or message.get('project_id') != carry['project_id']
                or message.get('session_id') != carry['session_id']):
            raise ValueError('Invalid carried record')
    if (sum(len(message['text']) for message in carry['part']) > max_chars
            or any(message.get('timestamp', '') != carry['timestamp'] for message in carry['deferred'])
            or len({message['id'] for message in carry['deferred']}) != len(carry['deferred'])):
        raise ValueError('Invalid carried ordering')
    _bounded(carry)


def _bounded(carry):
    if len(json.dumps(carry, ensure_ascii=False).encode('utf-8')) > MAX_CARRY_BYTES:
        raise ValueError('Resumable compaction staging limit reached; input remains pending')


def resume_compaction(messages, carry, *, session_end, max_chars):
    if type(max_chars) is not int or max_chars < 1 or type(session_end) is not bool:
        raise ValueError('Invalid compaction allowance')
    if carry is not None:
        _validate(carry, max_chars)
    state, sealed = copy.deepcopy(carry), []

    def seal(parts):
        for part in parts:
            sealed.append(dict(project_id=state['project_id'], session_id=state['session_id'],
                part=state['next_part'], messages=part, fingerprint=part_fingerprint(part)))
            state['next_part'] += 1

    def close_tie():
        parts, state['part'] = pack_records(sorted(state['deferred'], key=lambda message: message['id']),
                                            max_chars, state['part'])
        seal(parts)
        state['deferred'] = []

    for raw in messages:
        project = canonical_project(raw.get('project_id') or raw.get('project') or 'unknown')
        session = raw.get('session_id') or raw.get('path') or 'unknown'
        timestamp = raw.get('timestamp', '')
        if not isinstance(timestamp, str):
            raise ValueError('Invalid compaction ordering')
        if state is None:
            state = dict(version=1, max_chars=max_chars, project_id=project, session_id=session,
                         next_part=0, part=[], deferred=[], timestamp=timestamp)
        if project != state['project_id'] or session != state['session_id']:
            raise ValueError('Compaction page crosses sessions')
        if timestamp < state['timestamp']:
            raise ValueError('Compaction page precedes retained input')
        if timestamp > state['timestamp']:
            close_tie()
            state['timestamp'] = timestamp
        message = compact_message(raw)
        if message is not None:
            message.update(project_id=project, session_id=session)
            prior = next((item for item in state['deferred'] if item['id'] == message['id']), None)
            if prior is not None and prior != message:
                raise ValueError('Conflicting duplicate compaction record')
            if prior is None:
                state['deferred'].append(message)
        _bounded(state)
    if state is None:
        return dict(sealed=[], carry=None, next_part=0)
    if session_end:
        close_tie()
        if state['part']:
            seal([state['part']])
        return dict(sealed=sealed, carry=None, next_part=state['next_part'])
    return dict(sealed=sealed, carry=state, next_part=state['next_part'])
