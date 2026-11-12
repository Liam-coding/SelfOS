"""Contained, immutable original-document evidence for registered sources."""
import hashlib
import re
from pathlib import Path

from selfos.sources.text import redact

MAX_BYTES = 20 * 1024 * 1024
TEXT_SUFFIXES = {'.txt', '.md', '.json', '.jsonl'}


class SourceUnavailable(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def source_page(text, offset, limit):
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise SourceUnavailable('invalid_source_request', 'Invalid source offset')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 32000:
        raise SourceUnavailable('invalid_source_request', 'Invalid source page size')
    if offset > len(text):
        raise SourceUnavailable('invalid_source_request', 'Source offset is beyond the original text')
    end = min(offset + limit, len(text))
    return {'text': text[offset:end], 'text_offset': offset, 'text_total': len(text),
            'next_offset': end if end < len(text) else None, 'redacted': True}


def document_source(vault, source, offset=0, limit=24000):
    vault = Path(vault).resolve()
    value = source.get('path')
    if not isinstance(value, str) or not value:
        raise SourceUnavailable('source_unverified', 'Original source metadata is incomplete')
    path = Path(value.replace('\\', '/'))
    path = (path if path.is_absolute() else vault / path).resolve()
    original_root = (vault / '.knowledge_uploads' / 'originals').resolve()
    if not original_root.is_relative_to(vault) or not path.is_relative_to(original_root):
        raise SourceUnavailable('source_denied', 'Original source is outside the permitted import folder')
    if path.suffix.lower() not in TEXT_SUFFIXES:
        raise SourceUnavailable('unsupported_source_format', 'This original source format is not supported yet')
    expected = source.get('content_sha256')
    if not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected):
        raise SourceUnavailable('source_unverified', 'Original source has no verifiable content hash')
    if not path.is_file():
        raise SourceUnavailable('source_missing', 'Original source is missing or has moved')
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
    except OSError:
        raise SourceUnavailable('source_missing', 'Original source cannot be read') from None
    if len(raw) > MAX_BYTES:
        raise SourceUnavailable('source_too_large', 'Original source exceeds the supported size limit')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise SourceUnavailable('source_changed', 'Original source changed; its content cannot be verified')
    try:
        text = redact(raw.decode('utf-8-sig'))
    except UnicodeDecodeError:
        raise SourceUnavailable('source_encoding', 'Original source is not supported UTF-8 text') from None
    return source_page(text, offset, limit)
