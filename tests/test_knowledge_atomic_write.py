import os as _os
import selfos.storage.files as _storage_files
import pytest



def locked_error():
    error=PermissionError('Temporary Windows file lock');error.winerror=32
    return error


def test_atomic_write_retries_windows_lock_without_truncating_target(tmp_path,monkeypatch):
    target=tmp_path/'history.md';target.write_bytes(b'previous')
    original=_os.replace;calls=[]
    def replace(temp,path):
        calls.append(True)
        if len(calls)<=2:
            assert target.read_bytes()==b'previous'
            raise locked_error()
        return original(temp,path)
    monkeypatch.setattr(_os,'replace',replace)
    _storage_files._atomic_write(target,b'new')
    assert target.read_bytes()==b'new' and len(calls)==3
    assert sorted(p.name for p in tmp_path.iterdir())==['history.md']


def test_persistent_windows_lock_is_bounded_and_leaves_target_intact(tmp_path,monkeypatch):
    target=tmp_path/'history.md';target.write_bytes(b'previous');calls=[]
    def replace(*args):
        calls.append(True);raise locked_error()
    monkeypatch.setattr(_os,'replace',replace)
    with pytest.raises(PermissionError):_storage_files._atomic_write(target,b'new')
    assert 1<len(calls)<=5
    assert target.read_bytes()==b'previous'
    assert sorted(p.name for p in tmp_path.iterdir())==['history.md']


def test_other_replace_errors_are_not_retried(tmp_path,monkeypatch):
    calls=[]
    def replace(*args):
        calls.append(True);raise PermissionError('Permanent permission error')
    monkeypatch.setattr(_os,'replace',replace)
    with pytest.raises(PermissionError):_storage_files._atomic_write(tmp_path/'target',b'new')
    assert len(calls)==1
