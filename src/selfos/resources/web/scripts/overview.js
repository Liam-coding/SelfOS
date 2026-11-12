
async function updateKnowledgeOverview() {
  const status = document.getElementById('knowledge-overview-status');
  try {
    const response = await fetch('/__knowledge_settings__');
    if (!response.ok) throw new Error('Knowledge service unavailable');
    const data = await response.json();
    for (const key of ['cards','lessons','personal_facts','preferences','history']) {
      document.getElementById('knowledge-count-' + key).textContent = data.counts[key] || 0;
    }
    document.getElementById('knowledge-connection-dot').classList.add('ready');
    const english = document.documentElement.lang === 'en' || localStorage.getItem('selfos-lang') === 'en';
    status.textContent = data.saved_checkpoints
      ? (english ? data.saved_checkpoints + ' saved conversation parts · Original sources preserved' : '已保存 ' + data.saved_checkpoints + ' 个对话片段 · 原文保留，可继续整理')
      : (english ? 'Local knowledge · Sources and backups preserved' : '本地知识库 · 保留来源与备份');
  } catch (error) {
    document.getElementById('knowledge-connection-dot').classList.remove('ready');
    status.textContent = '暂时无法连接本地服务，请检查服务是否启动。';
  }
}
document.addEventListener('DOMContentLoaded', updateKnowledgeOverview);
