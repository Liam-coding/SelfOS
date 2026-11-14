"""Packaged upload controls and transport boundaries; real Chromium flow is optional."""
from html.parser import HTMLParser

from selfos.web.rendering.resources import frontend_text
from selfos.web.i18n import catalogs
import os
import subprocess
import sys
from pathlib import Path
import pytest


def test_upload_picker_has_native_input_and_distinct_cancel_and_organize_controls():
    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.elements = {}
        def handle_starttag(self, tag, attrs):
            value = dict(attrs)
            if 'id' in value:
                self.elements[value['id']] = tag, value
    parsed = Elements()
    parsed.feed(frontend_text('templates/uploads.html'))
    tag, picker = parsed.elements['uploads-files']
    assert tag == 'input' and picker['type'] == 'file' and 'multiple' in picker
    assert picker['accept'] == '.txt,.md'
    assert parsed.elements['uploads-choose'][0] == 'button'
    assert parsed.elements['uploads-organize'][0] == 'button'
    assert parsed.elements['uploads-cancel'][0] == 'button'
    assert parsed.elements['uploads-status'][1]['role'] == 'status'
    for locale in ('en', 'zh-CN'):
        messages = catalogs()['locales'][locale]['messages']
        for key in ('open', 'local_only', 'cancel_upload', 'organize', 'interrupted', 'login_required', 'too_many'):
            assert 'upload.' + key in messages


@pytest.mark.skipif(not os.environ.get('SELFOS_CHROMIUM'), reason='Optional isolated Chromium acceptance; run with SELFOS_CHROMIUM')
def test_picker_drop_cancel_locale_and_selected_organization_in_chromium(tmp_path):
    path = Path(__file__).parent / 'browser/uploads.py'
    result = subprocess.run([sys.executable, '-X', 'utf8', str(path), '--output', str(tmp_path),
        '--chromium', os.environ['SELFOS_CHROMIUM']], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not os.environ.get('SELFOS_CHROMIUM'), reason='Optional isolated Chromium source lifecycle')
def test_switching_original_clears_text_during_loading_failure_and_late_responses():
    path = Path(__file__).parent / 'browser/upload_source_display.py'
    result = subprocess.run([sys.executable, '-X', 'utf8', str(path),
        '--chromium', os.environ['SELFOS_CHROMIUM']], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cached_dashboard_refresh_keeps_one_upload_module(tmp_path):
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.web.rendering.refresh import refresh_dashboard
    vault = tmp_path / 'vault'
    vault.mkdir()
    page = generate_dashboard(vault).read_text(encoding='utf-8')
    for _ in range(2):
        page = refresh_dashboard(page)
        assert page.count('id="uploads-open"') == 1
        assert page.count('id="uploads-dialog"') == 1
