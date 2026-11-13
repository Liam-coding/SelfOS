"""Bounded, durable request allowances and measured provider usage; no prompts."""
import json
import math
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from selfos.storage.files import _atomic_write
from selfos.storage.onboarding import ModelBudgetExceeded


def _canonical(path):
    resolved = Path(path).resolve()
    # Windows may retain the extended prefix when an atomic replacement races
    # resolution. Normalize its spelling, retaining the containment check.
    if os.name == 'nt':
        text = str(resolved)
        prefix = chr(92) * 2 + '?' + chr(92)
        if text.startswith(prefix + 'UNC' + chr(92)):
            text = chr(92) * 2 + text[len(prefix) + 4:]
        elif text.startswith(prefix):
            text = text[len(prefix):]
        resolved = Path(text)
    return resolved


def _path(vault, name):
    root = _canonical(vault)
    path = root / name
    if not _canonical(path).is_relative_to(root):
        raise ValueError('Usage metadata escapes vault')
    return path


def _read(path, default, maximum=4 * 1024 * 1024):
    if not path.exists():
        return default
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Usage metadata exceeds size limit')
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError('Invalid usage metadata') from error


def _validate_budget(value):
    if not isinstance(value, dict) or set(value) - {'max_requests', 'input_price', 'output_price'}:
        raise ValueError('Invalid organization budget settings')
    limit = value.get('max_requests', 100)
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError('Request allowance must be 1..10000')
    result = {'max_requests': limit}
    for field in ('input_price', 'output_price'):
        price = value.get(field)
        if price is not None and (type(price) not in (int, float) or not math.isfinite(price) or not 0 <= price <= 100000):
            raise ValueError('Token price must be a finite nonnegative number')
        result[field] = price
    return result


@contextmanager
def _usage_lock(path):
    lock = path.with_suffix('.lock')
    if not _canonical(lock).is_relative_to(_canonical(path.parent)):
        raise ValueError('Usage lock escapes vault')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.seek(0, 2) == 0:
                stream.write(b'0')
                stream.flush()
            deadline = time.monotonic() + 10
            while True:
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Usage accounting is busy; retry later')
                    time.sleep(.01)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class RequestUsage:
    def __init__(self, vault, identity, limit, delegate=None):
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
            raise ValueError('Invalid usage identity')
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 10000):
            raise ValueError('Invalid request allowance')
        if limit is None and delegate is None:
            raise ValueError('An allowance is required')
        self.vault, self.identity, self.limit, self.delegate = vault, identity, limit, delegate
        self.path = _path(vault, f'.knowledge_usage/{identity}.json')

    def _read(self):
        value = _read(_path(self.vault, f'.knowledge_usage/{self.identity}.json'), {'version': 1, 'used': 0, 'attempts': {}, 'elapsed_seconds': 0, 'run_started': None})
        if (not isinstance(value, dict) or value.get('version') != 1 or type(value.get('used')) is not int
                or not 0 <= value['used'] <= 10000 or not isinstance(value.get('attempts'), dict)
                or set(value['attempts']) != {str(i) for i in range(1, value['used'] + 1)}):
            raise ValueError('Invalid usage journal')
        for key, attempt in value['attempts'].items():
            if (not isinstance(key, str) or not key.isdigit() or not 1 <= int(key) <= value['used']
                    or not isinstance(attempt, dict) or attempt.get('status') not in ('pending', 'response', 'failed')):
                raise ValueError('Invalid usage attempt')
            for field in ('input_tokens', 'output_tokens'):
                if attempt.get(field) is not None and (type(attempt[field]) is not int or not 0 <= attempt[field] <= 10**12):
                    raise ValueError('Invalid measured token usage')
        for key in ('elapsed_seconds', 'run_started'):
            number = value.get(key)
            if number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number < 0):
                raise ValueError('Invalid usage duration')
        return value

    def _write(self, value):
        raw = json.dumps(value).encode()
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('Usage journal exceeds size limit')
        _atomic_write(_path(self.vault, f'.knowledge_usage/{self.identity}.json'), raw)

    def claim(self):
        with _usage_lock(_path(self.vault, f'.knowledge_usage/{self.identity}.json')):
            value = self._read()
            if value['used'] >= (self.limit if self.limit is not None else 10000):
                raise ModelBudgetExceeded('Organization request allowance exhausted; saved work is retained. Raise the allowance explicitly to resume.')
            if self.delegate is not None:
                self.delegate.claim()
            value['used'] += 1
            value['attempts'][str(value['used'])] = {'status': 'pending'}
            self._write(value)
            return value['used']

    def observe(self, ticket, data, provider):
        usage = data.get('usage') if isinstance(data, dict) else None
        fields = ('input_tokens', 'output_tokens') if provider == 'anthropic' else ('prompt_tokens', 'completion_tokens')
        report = {'status': 'response'}
        if isinstance(usage, dict):
            for field, source in zip(('input_tokens', 'output_tokens'), fields):
                tokens = usage.get(source)
                if type(tokens) is int and 0 <= tokens <= 10**12:
                    report[field] = tokens
            details = usage.get('prompt_tokens_details', {})
            report['cache_billing_unknown'] = bool(usage.get('cache_read_input_tokens') or usage.get('cache_creation_input_tokens')
                or (isinstance(details, dict) and details.get('cached_tokens')))
        with _usage_lock(_path(self.vault, f'.knowledge_usage/{self.identity}.json')):
            value = self._read()
            previous = value['attempts'].get(str(ticket))
            if not previous:
                raise ValueError('Unknown request ticket')
            if previous['status'] == 'pending':
                value['attempts'][str(ticket)] = report
                self._write(value)

    def fail(self, ticket):
        with _usage_lock(_path(self.vault, f'.knowledge_usage/{self.identity}.json')):
            value = self._read()
            attempt = value['attempts'].get(str(ticket))
            if not attempt:
                raise ValueError('Unknown request ticket')
            attempt['status'] = 'failed'
            self._write(value)

    def timer(self, running):
        with _usage_lock(_path(self.vault, f'.knowledge_usage/{self.identity}.json')):
            value = self._read()
            if value.get('run_started') is not None:
                value['elapsed_seconds'] += max(0, time.time() - value['run_started'])
            value['run_started'] = time.time() if running else None
            self._write(value)

    def status(self):
        value = self._read()
        attempts = list(value['attempts'].values())
        missing = sum(any(field not in attempt for field in ('input_tokens', 'output_tokens')) for attempt in attempts)
        elapsed = value.get('elapsed_seconds', 0) + (max(0, time.time() - value['run_started']) if value.get('run_started') is not None else 0)
        return {'id': self.identity, 'used': value['used'], 'limit': self.limit,
            'remaining': max(0, self.limit - value['used']) if self.limit is not None else self.delegate.status()['remaining'],
            'failed_attempts': sum(attempt['status'] == 'failed' for attempt in attempts),
            'input_tokens': sum(attempt.get('input_tokens', 0) for attempt in attempts),
            'output_tokens': sum(attempt.get('output_tokens', 0) for attempt in attempts),
            'missing_usage': missing, 'complete_usage': missing == 0,
            'cache_billing_unknown': any(attempt.get('cache_billing_unknown') for attempt in attempts),
            'elapsed_seconds': elapsed}
