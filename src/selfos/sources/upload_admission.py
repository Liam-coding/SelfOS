"""Bounded local text-file admission; never invokes a model."""
import codecs
import hashlib
import os
import time
import uuid
from selfos.storage.uploads import MAX_BYTES, discard_transfer, register_document, upload_path, upload_root, validate_filename


def admit_document(vault, filename, stream, length, *, cancel=lambda: False):
    validate_filename(filename)
    if isinstance(length, bool) or not isinstance(length, int) or not 0 < length <= MAX_BYTES:
        raise ValueError('Invalid upload size')
    root = upload_root(vault)
    temporary = upload_path(root, 'incoming/' + uuid.uuid4().hex + '.tmp')
    temporary.parent.mkdir(parents=True, exist_ok=True)
    decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
    digest = hashlib.sha256()
    deadline = time.monotonic() + 30
    try:
        with temporary.open('xb') as output:
            remaining = length
            while remaining:
                if cancel() or time.monotonic() >= deadline:
                    raise ValueError('Upload interrupted')
                chunk = stream.read(min(65536, remaining))
                if not isinstance(chunk, bytes) or not chunk or len(chunk) > remaining:
                    raise ValueError('Incomplete upload body')
                text = decoder.decode(chunk)
                if chr(0) in text:
                    raise ValueError('Binary content is not supported')
                output.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            decoder.decode(b'', final=True)
            output.flush()
            os.fsync(output.fileno())
        if cancel():
            raise ValueError('Upload interrupted')
        return register_document(vault, temporary, filename, digest.hexdigest(), length)
    except UnicodeDecodeError:
        raise ValueError('Only UTF-8 text uploads are supported') from None
    finally:
        discard_transfer(vault, temporary)
