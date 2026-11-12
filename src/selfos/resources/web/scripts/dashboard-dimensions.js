// ── Dim icons ──
const DIM_ICONS = {
  career:'💼', work:'🛠', health:'💪', learning:'📚',
  research:'🔬', life:'🌿', family:'🏠'
};
let _currentDimKey = '';

function chatAboutDim() {
  document.getElementById('dim-modal').classList.remove('open');
  if (chatCollapsed) toggleChat();
  _sendChatSilent(window.selfosI18n.t('ui.dimension.discuss',{label:window.selfosI18n.t('ui.dimension.'+_currentDimKey)}));
}

function openDim(card) {
  const key   = card.dataset.key;
  const score = card.dataset.score;
  const color = card.dataset.color;
  _currentDimKey = key;

  // Show modal
  document.getElementById('dim-modal-icon').textContent  = DIM_ICONS[key] || '📊';
  window.selfosI18n.bindText('dim-modal-title',card.dataset.labelKey);
  const scoreEl = document.getElementById('dim-modal-score');
  window.selfosI18n.bindText(scoreEl,'ui.common.value',{value:score.trim()!==''&&Number.isFinite(Number(score))?Number(score):score});
  scoreEl.style.color = color;
  window.selfosI18n.bindText('dim-modal-status',card.dataset.statusKey);
  document.getElementById('dim-modal-status').style.color = color;
  window.selfosI18n.bindText('dim-modal-sugg',card.dataset.suggKey);
  document.getElementById('dim-modal').classList.add('open');

}
document.getElementById('dim-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) document.getElementById('dim-modal').classList.remove('open');
});

// Send a chat message without touching the input box
async function _sendChatSilent(text) {
  appendMsg(text, 'user');
  chatHistory.push({role:'user', content: text});
  const thinking = appendMsg('', 'ai');
  window.selfosI18n.bindText(thinking,'ui.chat.thinking');
  thinking.classList.add('thinking');
  try {
    const fetchPromise = fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: chatHistory})
    });
    const res = await fetchPromise;
    const data = await res.json();
    if(!res.ok||typeof data.reply!=='string'||!data.reply.trim())throw Error('chat_failed');
    thinking.remove();
    const reply = data.reply;
    appendMsg(reply, 'ai');
    chatHistory.push({role:'assistant', content: reply});
  } catch(e) {
    window.selfosI18n.bindText(thinking,'ui.chat.failed');
  }
}

