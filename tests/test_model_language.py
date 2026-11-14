import re
import shutil
import subprocess

import pytest

from selfos.web.rendering.model import CONTROLS


def test_model_dynamic_text_and_placeholders_follow_language_without_resetting_inputs(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the browser state regression')
    from selfos.web.i18n import runtime
    common = runtime().split('<script', 1)[1].split('>', 1)[1].split('</script>', 1)[0]
    from selfos.web.rendering.resources import frontend_text
    script = frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/settings-model.js')
    harness = r'''
const assert = require('node:assert/strict');
const listeners = {};
const elements = new Map();
const document = {documentElement: {lang: 'en'},
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {value:'',textContent:'',placeholder:'',dataset:{},isConnected:true,style:{},setAttribute(key,value){this[key]=value;},showModal(){}});
    return elements.get(id);
  },
  querySelector(){return null;},
  addEventListener(event,fn){(listeners[event] ||= []).push(fn);},
  querySelectorAll(){return [...elements.values()];},dispatchEvent(event){(listeners[event.type]||[]).forEach(fn=>fn(event));}};
global.window=global;global.document=document;global.localStorage={getItem:()=>null,setItem(){}};
const fire = () => (listeners['selfos-language'] || []).forEach(fn=>fn());
'''
    checks = r'''
const key=document.getElementById('model-key');
key.value='unsaved-secret';
key.dataset.i18nPlaceholder='ui.model.key_placeholder';
selfosI18n.translate();
showCurrentModel({provider:'anthropic',model:'',proxy_source:'direct',effective_proxy:{},has_api_key:true});
assert.match(document.getElementById('model-status').textContent,/Proxy source/);
assert.match(document.getElementById('current-model').textContent,/Default/);
assert.match(key.placeholder,/blank/);
selfosI18n.setLocale('zh');
assert.match(document.getElementById('model-status').textContent,/代理来源/);
assert.match(key.placeholder,/留空/);
assert.equal(key.value,'unsaved-secret');
selfosI18n.setLocale('en');
assert.match(document.getElementById('model-status').textContent,/Configured/);
assert.equal(key.value,'unsaved-secret');
modelStatus('testing');
assert.match(document.getElementById('model-status').textContent,/Testing/);
selfosI18n.setLocale('zh');
assert.match(document.getElementById('model-status').textContent,/正在测试/);
modelStatus('passed');
assert.match(document.getElementById('model-status').textContent,/通过/);
selfosI18n.setLocale('en');
assert.match(document.getElementById('model-status').textContent,/passed/);
modelStatus('request_failed');
assert.equal(document.getElementById('model-status').textContent,'Could not complete the request. Check model and network settings.');
selfosI18n.setLocale('fr');
assert.match(key.placeholder,/blank/);
'''
    source = tmp_path / 'model-language.js'
    source.write_text(harness + common + script + checks, encoding='utf-8')
    result = subprocess.run([node, str(source)], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
