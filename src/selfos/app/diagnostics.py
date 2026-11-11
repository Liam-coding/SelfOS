"""app / diagnostics responsibilities."""
from selfos.storage.files import _atomic_write
from selfos.sources.text import redact
import json
from urllib.error import HTTPError, URLError

def _record_model_error(vault, run_id, batch_index, attempt, batch, response, error):
    folder = vault / '.knowledge_errors' / run_id
    if not folder.resolve().is_relative_to(vault.resolve()):
        raise ValueError('Diagnostic path escapes vault')
    raw = getattr(error, 'raw_response', '')
    if response is not None:
        raw = json.dumps(response, ensure_ascii=False, default=str)
    record = {'batch': batch_index, 'attempt': attempt, 'error': redact(str(error)),
              'known_source_ids': sorted({message['id'] for message in batch}),
              'response_redacted': redact(raw)[:64000]}
    path = folder / f'{batch_index:06d}-{attempt}.json'
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2).encode('utf-8'))
    return path.relative_to(vault)


def _retryable_model_error(error):
    if isinstance(error, HTTPError):
        return error.code == 429 or 500 <= error.code < 600
    return isinstance(error, (ValueError, TimeoutError, URLError))
