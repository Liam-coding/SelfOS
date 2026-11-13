"""Bounded read-only measured request and token status; no source scans."""
import re
from itertools import islice
from selfos.app.budget import read_budget
from selfos.storage.usage import RequestUsage, _path


def usage_status(vault, config_root):
    budget = read_budget(vault, config_root)
    folder = _path(vault, '.knowledge_usage')
    candidates = list(islice(folder.glob('*.json'), 128))
    reports, diagnostics = [], 0
    try:
        candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    except OSError:
        diagnostics += 1
    for path in candidates[:20]:
        if not re.fullmatch('[a-f0-9]{32}', path.stem):
            continue
        try:
            meter = RequestUsage(vault, path.stem, budget['max_requests'])
            report = meter.status()
            reports.append(report)
        except (ValueError, OSError, RuntimeError):
            diagnostics += 1
    return {'budget': budget, 'runs': reports, 'diagnostics': diagnostics, 'bounded': len(candidates) >= 128}
