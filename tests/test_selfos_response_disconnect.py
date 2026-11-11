import io
import pytest
from selfos.web.server import Handler


def handler():
    value=Handler.__new__(Handler)
    value.send_response=lambda *args:None
    value.send_header=lambda *args:None
    value.end_headers=lambda:None
    value.wfile=io.BytesIO()
    return value


@pytest.mark.parametrize('error',[BrokenPipeError,ConnectionResetError,ConnectionAbortedError])
@pytest.mark.parametrize('phase',['headers','body'])
def test_normal_disconnect_does_not_escape_response_writer(error,phase):
    value=handler()
    def fail(*args):raise error('client closed request')
    if phase=='headers':value.end_headers=fail
    else:value.wfile.write=fail
    value._send_json(200,{'ok':True})


def test_unexpected_response_errors_still_surface():
    value=handler()
    def fail(*args):raise OSError('unexpected output failure')
    value.wfile.write=fail
    with pytest.raises(OSError,match='unexpected'):value._send_json(200,{'ok':True})


def test_connected_response_contains_complete_body():
    value=handler()
    value._send(200,b'complete content','text/plain')
    assert value.wfile.getvalue()==b'complete content'
