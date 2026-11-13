"""Authenticated raw-file transfer without the generic buffered body reader."""
import re
import time
import json
from urllib.parse import parse_qs, unquote, urlsplit

UPLOAD_TIMEOUT = 30


class _Transfer:
    def __init__(self, handler):
        self.handler = handler
        self.deadline = time.monotonic() + UPLOAD_TIMEOUT

    def read(self, size):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Upload timed out')
        self.handler.connection.settimeout(remaining)
        # read1 returns available bytes so a slow trickle cannot restart the deadline.
        return self.handler.rfile.read1(min(size, 65536))


class UploadRoutes:
    def _upload_post(self):
        self.close_connection = True
        if not self._local_request():
            return self._send_json(403, {'code': 'upload_forbidden'})
        if not self._auth_guard():
            return
        lengths = self.headers.get_all('Content-Length', [])
        if not lengths:
            return self._send_json(411, {'code': 'upload_length_required'})
        if (len(lengths) != 1 or not re.fullmatch('[0-9]+', lengths[0])
                or len(lengths[0]) > 10 or self.headers.get_all('Transfer-Encoding')):
            return self._send_json(400, {'code': 'upload_invalid_headers'})
        length = int(lengths[0])
        from selfos.storage.uploads import MAX_BYTES, validate_filename
        if length > MAX_BYTES:
            return self._send_json(413, {'code': 'upload_too_large'})
        if not length:
            return self._send_json(400, {'code': 'upload_empty'})
        types = self.headers.get_all('Content-Type', [])
        if len(types) != 1 or types[0].strip().casefold() != 'application/octet-stream':
            return self._send_json(415, {'code': 'upload_unsupported_type'})
        names = self.headers.get_all('X-SelfOS-Filename', [])
        try:
            if (len(names) != 1 or len(names[0]) > 1536
                    or re.search(r'%(?![a-fA-F0-9]{2})', names[0])):
                raise ValueError('Invalid filename header')
            filename = validate_filename(unquote(names[0], encoding='utf-8', errors='strict'))
        except (ValueError, UnicodeError):
            return self._send_json(400, {'code': 'upload_invalid_filename'})
        timeout = self.connection.gettimeout()
        try:
            from selfos.sources.upload_admission import admit_document
            result = admit_document(self.runtime.VAULT, filename, _Transfer(self), length,
                                    cancel=lambda: not self._session_alive())
            return self._send_json(200 if result['duplicate'] else 201, result)
        except TimeoutError:
            return self._send_json(408, {'code': 'upload_timeout'})
        except ValueError:
            if not self._session_alive():
                return self._send_json(401, {'code': 'login_required'})
            return self._send_json(400, {'code': 'upload_invalid_or_unavailable'})
        except OSError:
            return self._send_json(503, {'code': 'upload_unavailable'})
        finally:
            self.connection.settimeout(timeout)

    def _upload_list(self):
        try:
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if set(query) - {'offset', 'limit'} or any(len(values) != 1 for values in query.values()):
                raise ValueError('Invalid pagination')
            offset = int(query.get('offset', ['0'])[0])
            limit = int(query.get('limit', ['50'])[0])
            if offset < 0 or not 1 <= limit <= 100:
                raise ValueError('Invalid pagination')
        except ValueError:
            return self._send_json(400, {'code': 'upload_invalid_page'})
        try:
            from selfos.app.uploads import upload_status
            return self._send_json(200, upload_status(self.runtime.VAULT, offset, limit))
        except (OSError, ValueError):
            return self._send_json(503, {'code': 'upload_registry_unavailable'})

    def _upload_preview(self):
        self.close_connection = True
        with self.runtime.KNOWLEDGE_RUN_LOCK:
            if self.runtime.KNOWLEDGE_RUN['stop_file'] is not None:
                return self._send_json(409, {'code': 'upload_import_active'})
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not re.fullmatch('[0-9]{1,5}', lengths[0]) or not 0 < int(lengths[0]) <= 8192:
                    raise ValueError('Invalid preview size')
                if self.headers.get_all('Transfer-Encoding'):
                    raise ValueError('Invalid preview encoding')
                body = json.loads(self._read_body())
                if not isinstance(body, dict) or set(body) != {'ids'}:
                    raise ValueError('Invalid document selection')
                from selfos.app.uploads import upload_preview
                return self._send_json(200, upload_preview(self.runtime.VAULT, body['ids']))
            except (ValueError, TypeError, KeyError):
                return self._send_json(400, {'code': 'upload_preview_invalid'})
            except (OSError, RuntimeError):
                return self._send_json(503, {'code': 'upload_preview_unavailable'})

    def _upload_source(self):
        try:
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if set(query) - {'id', 'offset', 'limit'} or any(len(values) != 1 for values in query.values()):
                raise ValueError('Invalid source request')
            from selfos.app.uploads import upload_source
            result = upload_source(self.runtime.VAULT, query.get('id', [''])[0],
                                   int(query.get('offset', ['0'])[0]), int(query.get('limit', ['24000'])[0]))
            return self._send_json(200, result)
        except (ValueError, OSError) as error:
            code = getattr(error, 'code', 'upload_source_unavailable')
            return self._send_json(403 if code == 'upload_excluded' else 400, {'code': code})
