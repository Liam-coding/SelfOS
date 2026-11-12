"""web / rendering / knowledge responsibilities."""


def refresh_controls(html):
    """Refresh settings in previously generated dashboards without a new import."""
    import re
    return re.sub(r'<button class="harvest-btn" onclick="openKnowledgeSettings\(\)"[^>]*>.*?<script>\s*let knowledgeOperation.*?</script>',
                  lambda _:CONTROLS.rstrip(),html,count=1,flags=re.S)


CONTROLS = r'''<button class="harvest-btn" onclick="openKnowledgeSettings()" data-zh="整理设置" data-en="Import settings">Import settings</button>
<dialog id="knowledge-settings" style="background:var(--bg,#fff);color:var(--text,#222);border-radius:16px;max-width:560px;padding:24px">
  <h3 data-zh="知识库整理设置" data-en="Knowledge import settings">Knowledge import settings</h3>
  <p data-zh="关注领域决定保留范围；原始对话保留。详细程度控制表达粒度，不设知识总数。" data-en="Focus domains determine what to retain. Original conversations are preserved. Detail controls how much context to keep, not the number of records.">Focus domains determine what to retain. Original conversations are preserved. Detail controls how much context to keep, not the number of records.</p>
  <div id="knowledge-domains"></div>
  <p><label><span data-zh="自定义领域（逗号分隔）" data-en="Custom domains (comma-separated)">Custom domains (comma-separated)</span> <input id="knowledge-custom" placeholder="For example: music, travel"></label></p>
  <p><label><span data-zh="详细程度" data-en="Detail level">Detail level</span> <select id="knowledge-detail"><option value="concise" data-zh="简洁" data-en="Concise">Concise</option><option value="balanced" data-zh="标准" data-en="Balanced">Balanced</option><option value="detailed" data-zh="详细" data-en="Detailed">Detailed</option></select></label></p>
  <p id="knowledge-status" role="status"></p>
  <button onclick="saveKnowledgeSettings(false)" data-zh="保存设置" data-en="Save settings">Save settings</button>
  <button onclick="saveKnowledgeSettings(true)" data-zh="保存并重建" data-en="Save and rebuild">Save and rebuild</button>
  <button id="knowledge-undo" onclick="undoKnowledge()" data-zh="撤销上次整理" data-en="Undo last import">Undo last import</button>
  <button onclick="document.getElementById('knowledge-settings').close()" data-zh="关闭" data-en="Close">Close</button>
</dialog>
<script>
let knowledgeOperation = null;
let knowledgeStatusTranslation = null;
const knowledgeDomains = {work:['工作','Work'],research:['研究','Research'],learning:['学习','Learning'],personal:['个人信息与偏好','Personal facts and preferences'],life:['生活','Life'],health:['健康','Health']};
const knowledgeText = (zh,en) => document.documentElement.lang === 'zh' ? zh : en;
function setKnowledgeStatus(zh,en) {
  knowledgeStatusTranslation=[zh,en];
  document.getElementById('knowledge-status').textContent=knowledgeText(zh,en);
}
function knowledgeSettingsError(error) {
  knowledgeStatusTranslation=null;
  document.getElementById('knowledge-status').textContent=error.message;
}
function translateKnowledgeSettings() {
  document.querySelectorAll('#knowledge-domains [data-domain]').forEach(span=>{
    span.textContent=knowledgeText(...knowledgeDomains[span.dataset.domain]);
  });
  document.getElementById('knowledge-custom').placeholder=knowledgeText('例如：音乐, 旅行','For example: music, travel');
  if(knowledgeStatusTranslation)document.getElementById('knowledge-status').textContent=knowledgeText(...knowledgeStatusTranslation);
}
document.addEventListener('selfos-language',translateKnowledgeSettings);
document.addEventListener('DOMContentLoaded',translateKnowledgeSettings);
async function knowledgeRequest(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || knowledgeText('请求失败','Request failed'));
  return data;
}
function displayKnowledgeStatus(data) {
  renderImportPublication(data);
  knowledgeOperation = data.last_operation ? data.last_operation.id : null;
  document.getElementById('knowledge-undo').disabled = !knowledgeOperation;
  if(data.needs_rebuild)setKnowledgeStatus('设置已变化，下次整理会自动重建。','Settings changed. The next import will rebuild automatically.');
  else setKnowledgeStatus('设置已保存。','Settings saved.');
}
async function openKnowledgeSettings() {
  const dialog = document.getElementById('knowledge-settings');
  dialog.showModal();
  setKnowledgeStatus('正在加载设置…','Loading settings…');
  try {
    const data = await knowledgeRequest('/__knowledge_settings__');
    const container = document.getElementById('knowledge-domains');
    container.replaceChildren();
    for (const [key, title] of Object.entries(knowledgeDomains)) {
      const label = document.createElement('label');
      label.style.marginRight = '12px';
      const input = document.createElement('input');
      input.type = 'checkbox'; input.value = key; input.checked = data.settings.domains.includes(key);
      const span=document.createElement('span');span.dataset.domain=key;span.textContent=knowledgeText(...title);
      label.append(input,span); container.append(label);
    }
    document.getElementById('knowledge-custom').value = data.settings.domains.filter(d => !(d in knowledgeDomains)).join(', ');
    document.getElementById('knowledge-detail').value = data.settings.detail;
    displayKnowledgeStatus(data);
  } catch (error) { knowledgeSettingsError(error); }
}
async function saveKnowledgeSettings(rebuild) {
  try {
    const domains = [...document.querySelectorAll('#knowledge-domains input:checked')].map(e => e.value);
    domains.push(...document.getElementById('knowledge-custom').value.split(/[,，]/).map(s => s.trim()).filter(Boolean));
    const data = await knowledgeRequest('/__knowledge_settings__', {domains:[...new Set(domains)],detail:document.getElementById('knowledge-detail').value});
    displayKnowledgeStatus(data);
    if (rebuild) { document.getElementById('knowledge-settings').close(); confirmHarvest(false, true, true); }
  } catch (error) { knowledgeSettingsError(error); }
}
async function undoKnowledge() {
  const button = document.getElementById('knowledge-undo'); button.disabled = true;
  try {
    const data = await knowledgeRequest('/__knowledge_restore__', {operation_id:knowledgeOperation});
    displayKnowledgeStatus(data);
    setKnowledgeStatus('上次整理已撤销，备份保留。','Last import undone. Backups are retained.');
  } catch (error) { knowledgeSettingsError(error); button.disabled = !knowledgeOperation; }
}
</script>
'''

from selfos.web.rendering.import_status import HTML as PUBLICATION_HTML, SCRIPT as PUBLICATION_SCRIPT
CONTROLS = CONTROLS.replace('<dialog id="knowledge-settings"', PUBLICATION_HTML + '\n<dialog id="knowledge-settings"', 1)
CONTROLS = CONTROLS.replace('<div id="knowledge-domains">', '<p id="import-modal-published" role="status"></p><p id="import-modal-boundary"></p><div id="knowledge-domains">', 1)
CONTROLS = CONTROLS.replace('let knowledgeOperation = null;', 'let knowledgeOperation = null;\n' + PUBLICATION_SCRIPT, 1)
