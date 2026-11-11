"""Shared dashboard controls, embedded unchanged by the dashboard generator."""
CONTROLS = r'''<button class="harvest-btn" onclick="openKnowledgeSettings()">整理设置</button>
<dialog id="knowledge-settings" style="background:var(--bg,#fff);color:var(--text,#222);border-radius:16px;max-width:560px;padding:24px">
  <h3>知识库整理设置</h3>
  <p>关注领域决定保留范围；原始对话保留。详细程度控制表达粒度，不设知识总数。</p>
  <div id="knowledge-domains"></div>
  <p><label>自定义领域（逗号分隔） <input id="knowledge-custom" placeholder="例如：音乐, 旅行"></label></p>
  <p><label>详细程度 <select id="knowledge-detail"><option value="concise">简洁</option><option value="balanced">标准</option><option value="detailed">详细</option></select></label></p>
  <p id="knowledge-status" role="status"></p>
  <button onclick="saveKnowledgeSettings(false)">保存设置</button>
  <button onclick="saveKnowledgeSettings(true)">保存并重建</button>
  <button id="knowledge-undo" onclick="undoKnowledge()">撤销上次整理</button>
  <button onclick="document.getElementById('knowledge-settings').close()">关闭</button>
</dialog>
<script>
let knowledgeOperation = null;
const knowledgeDomains = {work:'工作',research:'研究',learning:'学习',personal:'个人信息与偏好',life:'生活',health:'健康'};
async function knowledgeRequest(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}
function displayKnowledgeStatus(data) {
  knowledgeOperation = data.last_operation ? data.last_operation.id : null;
  document.getElementById('knowledge-undo').disabled = !knowledgeOperation;
  document.getElementById('knowledge-status').textContent = data.needs_rebuild ? '设置已变化，下次整理会自动重建。' : '设置已保存。';
}
async function openKnowledgeSettings() {
  const dialog = document.getElementById('knowledge-settings');
  dialog.showModal();
  try {
    const data = await knowledgeRequest('/__knowledge_settings__');
    const container = document.getElementById('knowledge-domains');
    container.replaceChildren();
    for (const [key, title] of Object.entries(knowledgeDomains)) {
      const label = document.createElement('label');
      label.style.marginRight = '12px';
      const input = document.createElement('input');
      input.type = 'checkbox'; input.value = key; input.checked = data.settings.domains.includes(key);
      label.append(input, document.createTextNode(title)); container.append(label);
    }
    document.getElementById('knowledge-custom').value = data.settings.domains.filter(d => !(d in knowledgeDomains)).join(', ');
    document.getElementById('knowledge-detail').value = data.settings.detail;
    displayKnowledgeStatus(data);
  } catch (error) { document.getElementById('knowledge-status').textContent = error.message; }
}
async function saveKnowledgeSettings(rebuild) {
  try {
    const domains = [...document.querySelectorAll('#knowledge-domains input:checked')].map(e => e.value);
    domains.push(...document.getElementById('knowledge-custom').value.split(/[,，]/).map(s => s.trim()).filter(Boolean));
    const data = await knowledgeRequest('/__knowledge_settings__', {domains:[...new Set(domains)],detail:document.getElementById('knowledge-detail').value});
    displayKnowledgeStatus(data);
    if (rebuild) { document.getElementById('knowledge-settings').close(); confirmHarvest(false, true, true); }
  } catch (error) { document.getElementById('knowledge-status').textContent = error.message; }
}
async function undoKnowledge() {
  const button = document.getElementById('knowledge-undo'); button.disabled = true;
  try {
    const data = await knowledgeRequest('/__knowledge_restore__', {operation_id:knowledgeOperation});
    displayKnowledgeStatus(data);
    document.getElementById('knowledge-status').textContent = '上次整理已撤销，备份保留。';
  } catch (error) { document.getElementById('knowledge-status').textContent = error.message; button.disabled = !knowledgeOperation; }
}
</script>
'''
