function progressStatus(key){window.selfosI18n.bindText('progress-title',key);}
// ── Harvest modal ──
function openHarvestModal() {
  document.getElementById('harvest-modal').classList.add('open');
}
function closeHarvestModal() {
  document.getElementById('harvest-modal').classList.remove('open');
}
let importRunning = false;
let knowledgeRecoveryGeneration = 0;
function recoverKnowledgeRun() {
  const generation = ++knowledgeRecoveryGeneration;
  importRunning = true;
  const bar = document.getElementById('progress-bar');
  const stopBtn = document.getElementById('knowledge-stop-btn');
  const title = document.getElementById('progress-title');
  const icon = document.getElementById('progress-icon');
  const doneBtn = document.getElementById('progress-done-btn');
  document.getElementById('progress-modal').classList.add('open');
  doneBtn.style.display = 'none';
  stopBtn.style.display = 'block';
  stopBtn.disabled = false;
  progressStatus('ui.import.checking_knowledge_task_status');
  async function recover() {
    try {
      const response = await fetch('/__knowledge_run__', {cache: 'no-store'});
      if (!response.ok) throw new Error('Status unavailable');
      const state = await response.json();
      if (generation !== knowledgeRecoveryGeneration) return;
      if (state.total) bar.style.width = Math.max(parseFloat(bar.style.width) || 0,
        10 + Math.round(80 * state.completed / state.total)) + '%';
      if (state.running) {
        progressStatus(state.phase==='stopping'?'ui.import.stopping_and_saving_progress':'ui.import.task_is_running_syncing_status');
        setTimeout(recover, 1500);
        return;
      }
      const result = state.result || {ok: false};
      importRunning = false;
      stopBtn.style.display = 'none';
      if (result.ok && !result.cancelled) bar.style.width = '100%';
      icon.textContent = result.ok && !result.cancelled ? '✅' : '⚠️';
      progressStatus(result.cancelled?'ui.import.stopped_progress_saved_resume_available':result.ok?'ui.import.knowledge_complete':'ui.import.incomplete_retry_available');
      doneBtn.style.display = 'block';
      window.selfosI18n.bindText(doneBtn,'ui.import.done_refresh');
      checkStaging();
      document.dispatchEvent(new Event('selfos-import-finished'));
    } catch (error) {
      if (generation !== knowledgeRecoveryGeneration) return;
      progressStatus('ui.import.server_unavailable_retrying_status');
      setTimeout(recover, 2000);
    }
  }
  recover();
}
// A reload attaches to a live task without launching an import.
fetch('/__knowledge_run__', {cache: 'no-store'}).then(response => response.ok ? response.json() : null)
  .then(state => { if (state && state.running && !importRunning) recoverKnowledgeRun(); }).catch(() => {});
async function stopKnowledge() {
  const btn = document.getElementById('knowledge-stop-btn');
  btn.disabled = true;
  try {
    const response = await fetch('/__knowledge_stop__', {method: 'POST'});
    if (!response.ok) throw new Error('Stop request failed');
    progressStatus('ui.import.stopping_saving_completed_results');
  } catch (error) {
    btn.disabled = false;
    progressStatus('ui.import.stop_failed');
  }
}

function confirmHarvest(full, knowledge = false, rebuild = false) {
  if (importRunning) return;
  ++knowledgeRecoveryGeneration;
  importRunning = true;
  const stopBtn = document.getElementById('knowledge-stop-btn');
  stopBtn.disabled = false;
  stopBtn.style.display = knowledge ? 'block' : 'none';
  closeHarvestModal();
  // show progress modal
  const pm = document.getElementById('progress-modal');
  const bar = document.getElementById('progress-bar');
  const log = document.getElementById('progress-log');
  const icon = document.getElementById('progress-icon');
  const title = document.getElementById('progress-title');
  const doneBtn = document.getElementById('progress-done-btn');
  bar.style.width = '0%';
  log.textContent = '';
  icon.textContent = '⏳';
  progressStatus(knowledge?'ui.import.building_knowledge':'ui.import.harvesting');
  doneBtn.style.display = 'none';
  pm.classList.add('open');

  // progress steps map keywords → approximate % complete
  const STEPS = [
    ['SelfOS Harvest', 5],
    ['Extracting', 20],
    ['extraction', 30],
    ['build_session', 50],
    ['digest', 60],
    ['Scoring', 75],
    ['Dashboard', 88],
    ['Done', 100],
  ];
  let pct = 0;
  const savedSessions = new Set();
  function advanceTo(n) {
    if (n > pct) { pct = n; bar.style.width = pct + '%'; }
  }

  const url = knowledge ? '/__knowledge_stream__' + (rebuild ? '?action=rebuild' : '') : '/__harvest_stream__?full=' + (full ? '1' : '0');
  const es = new EventSource(url);
  es.onmessage = function(e) {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.done) {
      es.close();
      importRunning = false;
      stopBtn.style.display = 'none';
      if (msg.ok && !msg.cancelled) advanceTo(100);
      icon.textContent = msg.ok ? '✅' : '⚠️';
      progressStatus(msg.ok?(knowledge?'ui.import.knowledge_complete':'ui.import.harvest_complete'):'ui.import.incomplete_retry_available');
      if (msg.cancelled) progressStatus('ui.import.stopped_resume_available');
      if (msg.ok) checkStaging();
      if (knowledge) document.dispatchEvent(new Event('selfos-import-finished'));
      doneBtn.style.display = 'block';
      window.selfosI18n.bindText(doneBtn,'ui.import.done_refresh');
      return;
    }
    const line = msg.line || '';
    if (line.trim()) {
      log.textContent += (log.textContent ? '\n' : '') + line;
      log.scrollTop = log.scrollHeight;
      if (knowledge) {
        const batch = line.match(/(?:Organizing|Saved) (?:batch|session) (\d+)\/(\d+)/);
        if (batch) {
          if (line.startsWith('Saved')) savedSessions.add(batch[1]);
          const completed = savedSessions.size;
          advanceTo(10 + Math.round(80 * completed / Number(batch[2])));
        } else if (line.includes('Knowledge:')) advanceTo(10);
      } else {
        for (const [kw, p] of STEPS) {
          if (line.toLowerCase().includes(kw.toLowerCase())) { advanceTo(p); break; }
        }
      }
    }
  };
  es.onerror = function() {
    es.close();
    if (knowledge) {
      recoverKnowledgeRun();
      return;
    }
    importRunning = false;
    icon.textContent = '⚠️';
    progressStatus('ui.import.connection_lost');
    doneBtn.style.display = 'block';
  };
}
document.getElementById('harvest-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeHarvestModal();
});

