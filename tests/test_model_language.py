import re
import shutil
import subprocess

import pytest

from selfos.web.rendering.model import CONTROLS


def test_model_dynamic_text_and_placeholders_follow_language_without_resetting_inputs():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to execute the browser state regression')
    script = re.search(r'<script>(.*?)</script>', CONTROLS, re.S)[1]
    harness = r'''
const assert = require('node:assert/strict');
const listeners = {};
const elements = new Map();
const document = {documentElement: {lang: 'en'},
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {value:'',textContent:'',placeholder:'',dataset:{},style:{},showModal(){}});
    return elements.get(id);
  },
  querySelector(){return null;},
  addEventListener(event,fn){(listeners[event] ||= []).push(fn);},
  querySelectorAll(){return [];}};
const fire = () => (listeners['selfos-language'] || []).forEach(fn=>fn());
'''
    checks = r'''
const key=document.getElementById('model-key');
key.value='unsaved-secret';
showCurrentModel({provider:'anthropic',model:'',proxy_source:'direct',effective_proxy:{},has_api_key:true});
assert.match(document.getElementById('model-status').textContent,/Proxy source/);
assert.match(document.getElementById('current-model').textContent,/Default/);
assert.match(key.placeholder,/blank/);
document.documentElement.lang='zh';fire();
assert.match(document.getElementById('model-status').textContent,/代理来源/);
assert.match(key.placeholder,/留空/);
assert.equal(key.value,'unsaved-secret');
document.documentElement.lang='en';fire();
assert.match(document.getElementById('model-status').textContent,/Configured/);
assert.equal(key.value,'unsaved-secret');
setModelStatus({key:'testing'});
assert.match(document.getElementById('model-status').textContent,/Testing/);
document.documentElement.lang='zh';fire();
assert.match(document.getElementById('model-status').textContent,/正在测试/);
setModelStatus({key:'passed'});
assert.match(document.getElementById('model-status').textContent,/通过/);
document.documentElement.lang='en';fire();
assert.match(document.getElementById('model-status').textContent,/passed/);
setModelStatus({error:'HTTP 401'});
assert.equal(document.getElementById('model-status').textContent,'Request failed: HTTP 401');
document.documentElement.lang='fr';fire();
assert.match(key.placeholder,/blank/);
'''
    result = subprocess.run([node, '-e', harness + script + checks], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
