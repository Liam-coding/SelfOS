"""Ephemeral knowledge job state and nonblocking subprocess output."""
import queue
import re
import threading
import os
import sys
from pathlib import Path

def command(name, root, *options):
    if name not in ('knowledge', 'harvest'):
        raise ValueError('Unsupported background command')
    return [sys.executable, '-u', '-m', 'selfos', name, '--root', str(Path(root).resolve()), *options]

def child_environment():
    import selfos
    environment = os.environ.copy()
    # Checkout execution needs src on the child's search path. This also works
    # for installed packages; the data directory never determines import paths.
    package_parent = str(Path(selfos.__file__).resolve().parent.parent)
    current = environment.get('PYTHONPATH', '')
    environment['PYTHONPATH'] = package_parent + (os.pathsep + current if current else '')
    environment['PYTHONIOENCODING'] = 'utf-8'
    return environment

def knowledge_run_status(run_state, lock):
    """Return only public, ephemeral task metadata; never expose process or paths."""
    with lock:
        run = run_state
        marker = run.get('stop_file')
        proc = run.get('process')
        running = marker is not None
        phase = run.get('phase', 'idle')
        if running:
            phase = ('stopping' if marker.exists() else
                     'starting' if proc is None else
                     'finishing' if proc.poll() is not None else 'running')
        return dict(running=running, phase=phase, job_id=run.get('job_id'),
                    completed=len(run.get('saved', set())), total=run.get('total', 0),
                    last_line=run.get('last_line', ''), result=run.get('result'))

def knowledge_run_line(line, run_state, lock):
    with lock:
        run_state['last_line'] = line[:2000]
        total = re.search(r'Knowledge: \d+ compact session parts, (\d+) pending', line)
        if total: run_state['total'] = int(total.group(1))
        saved = re.search(r'Saved (?:session|batch) (\d+)/(\d+)', line)
        if saved:
            run_state.setdefault('saved', set()).add(int(saved.group(1)))
            run_state['total'] = int(saved.group(2))

def process_lines(proc, on_line=None, heartbeat=10):
    """Drain stdout independently so a quiet child never blocks SSE heartbeats."""
    output=queue.Queue()
    def read():
        try:
            while True:
                line=proc.stdout.readline()
                if line=='':break
                if on_line is not None: on_line(line.rstrip('\n'))
                output.put(('line',line))
            output.put(('done',None))
        except Exception as error:output.put(('error',error))
    reader = threading.Thread(target=read,daemon=True)
    proc._selfos_output_reader = reader
    reader.start()
    while True:
        try:kind,value=output.get(timeout=heartbeat)
        except queue.Empty:
            yield None
            continue
        if kind=='error':raise value
        if kind=='done':
            if proc.poll() is None:proc.wait()
            return
        yield value
