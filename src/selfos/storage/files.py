"""storage / files responsibilities."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time

def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        stream.write(data)
    try:
        for attempt in range(5):
            try:
                os.replace(temp,path)
                break
            except PermissionError as error:
                if getattr(error,'winerror',None) not in (5,32,33) or attempt==4:raise
                time.sleep(0.02*(2**attempt))
    finally:
        if temp.exists():
            temp.unlink()


def _read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


@contextmanager
def _locked(vault):
    vault.mkdir(parents=True, exist_ok=True)
    lock = vault / '.knowledge.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        owner = lock.read_text().strip()
        if not owner.isdigit() or _pid_alive(int(owner)):
            raise RuntimeError('A knowledge import or restore is already running.')
        lock.unlink()
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _pid_alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
