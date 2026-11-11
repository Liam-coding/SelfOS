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
  title.textContent = lang === 'zh' ? '正在核实整理任务状态…' : 'Checking knowledge task status…';
  async function recover() {
    try {
      const response = await fetch('/__knowledge_run__', {cache: 'no-store'});
      if (!response.ok) throw new Error('Status unavailable');
      const state = await response.json();
      if (generation !== knowledgeRecoveryGeneration) return;
      if (state.total) bar.style.width = Math.max(parseFloat(bar.style.width) || 0,
        10 + Math.round(80 * state.completed / state.total)) + '%';
      if (state.running) {
        title.textContent = state.phase === 'stopping'
          ? (lang === 'zh' ? '正在停止并保存进度…' : 'Stopping and saving progress…')
          : (lang === 'zh' ? '整理任务仍在运行，正在同步状态…' : 'Task is running; syncing status…');
        setTimeout(recover, 1500);
        return;
      }
      const result = state.result || {ok: false};
      importRunning = false;
      stopBtn.style.display = 'none';
      if (result.ok && !result.cancelled) bar.style.width = '100%';
      icon.textContent = result.ok && !result.cancelled ? '✅' : '⚠️';
      title.textContent = result.cancelled
        ? (lang === 'zh' ? '已停止，已保存进度，可继续整理' : 'Stopped; progress saved, resume available')
        : result.ok ? (lang === 'zh' ? '知识库整理完成' : 'Knowledge complete')
        : (lang === 'zh' ? '整理未完成，可重试' : 'Incomplete; retry available');
      doneBtn.style.display = 'block';
      doneBtn.textContent = lang === 'zh' ? '完成，刷新页面' : 'Done, Refresh';
      checkStaging();
    } catch (error) {
      if (generation !== knowledgeRecoveryGeneration) return;
      title.textContent = lang === 'zh' ? '暂时无法连接服务，正在重试状态查询…' : 'Server unavailable; retrying status…';
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
    document.getElementById('progress-title').textContent = lang === 'zh'
      ? '正在停止，保存已完成结果…' : 'Stopping; saving completed results…';
  } catch (error) {
    btn.disabled = false;
    document.getElementById('progress-log').textContent += String.fromCharCode(10) + error.message;
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
  title.textContent = knowledge
    ? (lang === 'zh' ? '正在整理知识库…' : 'Building knowledge…')
    : (lang === 'zh' ? '采集中…' : 'Harvesting…');
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
      title.textContent = msg.ok
        ? (lang === 'zh' ? (knowledge ? '知识库整理完成' : '采集完成') : 'Done')
        : (lang === 'zh' ? (knowledge ? '整理未完成，可重试' : '采集出错') : 'Error — retry available');
      if (msg.cancelled) title.textContent = lang === 'zh' ? '已停止，可继续整理' : 'Stopped; resume available';
      if (msg.ok) checkStaging();
      doneBtn.style.display = 'block';
      doneBtn.textContent = lang === 'zh' ? '完成，刷新页面' : 'Done, Refresh';
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
    title.textContent = lang === 'zh' ? '连接中断' : 'Connection lost';
    doneBtn.style.display = 'block';
  };
}
document.getElementById('harvest-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeHarvestModal();
});
