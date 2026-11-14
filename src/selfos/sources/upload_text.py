"""Versioned redacted coordinates and conservative document evidence projection."""
import hashlib
import time

from selfos.sources.documents import document_text, NORMALIZATION_VERSION
from selfos.knowledge.filtering import compact_message
from selfos.knowledge.identity import digest

MAX_NORMALIZED_BYTES = 80 * 1024 * 1024


def normalize_document(vault, document):
    started = time.monotonic()
    text = document_text(vault, document)
    if len(text.encode('utf-8')) > MAX_NORMALIZED_BYTES or time.monotonic() - started > 30:
        raise ValueError('Document normalization exceeds local limits')
    return text


def document_part(document, text, text_hash, profile, number, part_chars):
    start, end = number * part_chars, min((number + 1) * part_chars, len(text))
    messages = []
    for offset in range(start, end, 4096):
        boundary = min(offset + 4096, end)
        piece = text[offset:boundary]
        message = dict(id=digest([document['id'], NORMALIZATION_VERSION, offset, boundary, piece]),
            text=piece, source='uploaded_file', role='user', provenance='quoted_dialogue',
            project_id='uploaded-document:' + document['id'],
            session_id='uploaded-document:' + document['id'] + ':' + profile,
            path=document['path'], original_filename=document['original_filename'],
            content_sha256=document['content_sha256'], document_id=document['id'],
            timestamp=document['uploaded_at'], timestamp_kind='import_time',
            normalization_version=NORMALIZATION_VERSION, text_sha256=text_hash,
            text_start=offset, text_end=boundary)
        compacted = compact_message(message)
        if compacted:
            messages.append(compacted)
    result = dict(project_id='uploaded-document:' + document['id'],
                session_id='uploaded-document:' + document['id'] + ':' + profile,
                part=number, messages=messages, partial_input=True,
                fingerprint=digest(['uploaded-part-v1', messages]))
    result.update(upload_document_id=document['id'], upload_profile=profile,
                  upload_part_id=digest([document['id'], profile, number, result['fingerprint']]))
    return result
