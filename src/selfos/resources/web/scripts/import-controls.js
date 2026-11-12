
let knowledgeOperation = null;

const knowledgeDomains = {work:'ui.import_settings.work',research:'ui.import_settings.research',learning:'ui.import_settings.learning',personal:'ui.import_settings.personal_facts_and_preferences',life:'ui.import_settings.life',health:'ui.import_settings.health'};
function setKnowledgeStatus(key){window.selfosI18n.bindText('knowledge-status',key);}
function knowledgeSettingsError(error){setKnowledgeStatus('ui.import_settings.request_failed');}
async function knowledgeRequest(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(window.selfosI18n.t('ui.import_settings.request_failed'));
  return data;
}
function displayKnowledgeStatus(data) {
  if(typeof renderImportPublication==='function')renderImportPublication(data);
  knowledgeOperation = data.last_operation ? data.last_operation.id : null;
  document.getElementById('knowledge-undo').disabled = !knowledgeOperation;
  if(data.needs_rebuild)setKnowledgeStatus('ui.import_settings.settings_changed_the_next_import_will_rebuild_automatically');
  else setKnowledgeStatus('ui.import_settings.settings_saved');
}
async function openKnowledgeSettings() {
  const dialog = document.getElementById('knowledge-settings');
  dialog.showModal();
  setKnowledgeStatus('ui.import_settings.loading_settings');
  try {
    const data = await knowledgeRequest('/__knowledge_settings__');
    const container = document.getElementById('knowledge-domains');
    container.replaceChildren();
    for (const [key, title] of Object.entries(knowledgeDomains)) {
      const label = document.createElement('label');
      label.style.marginRight = '12px';
      const input = document.createElement('input');
      input.type = 'checkbox'; input.value = key; input.checked = data.settings.domains.includes(key);
      const span=document.createElement('span');span.dataset.domain=key;window.selfosI18n.bindText(span,title);
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
    setKnowledgeStatus('ui.import_settings.last_import_undone_backups_are_retained');
  } catch (error) { knowledgeSettingsError(error); button.disabled = !knowledgeOperation; }
}
