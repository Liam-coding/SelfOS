// ── Dim icons ──
const DIM_ICONS = {
  career:'💼', work:'🛠', health:'💪', learning:'📚',
  research:'🔬', life:'🌿', family:'🏠'
};
let _currentDimKey = '';
let _pendingDimMsg = '';

function chatAboutDim() {
  document.getElementById('dim-modal').classList.remove('open');
  if (chatCollapsed) toggleChat();
  _sendChatSilent(_pendingDimMsg);
}

function openDim(card) {
  const key   = card.dataset.key;
  const score = card.dataset.score;
  const color = card.dataset.color;
  _currentDimKey = key;
  const label = card.dataset[lang === 'zh' ? 'labelZh' : 'labelEn'];

  // Show modal
  document.getElementById('dim-modal-icon').textContent  = DIM_ICONS[key] || '📊';
  document.getElementById('dim-modal-title').textContent = label;
  const scoreEl = document.getElementById('dim-modal-score');
  scoreEl.textContent = score;
  scoreEl.style.color = color;
  document.getElementById('dim-modal-status').textContent = card.dataset[lang === 'zh' ? 'statusZh' : 'statusEn'];
  document.getElementById('dim-modal-status').style.color = color;
  document.getElementById('dim-modal-sugg').textContent   = card.dataset[lang === 'zh' ? 'suggZh' : 'suggEn'];
  document.getElementById('dim-modal').classList.add('open');

  // Pre-store the message so the chat button can send it
  _pendingDimMsg = lang === 'zh' ? `帮我分析一下「${label}」这个维度` : `Tell me about my ${label} dimension`;
}
document.getElementById('dim-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) document.getElementById('dim-modal').classList.remove('open');
});

// Send a chat message without touching the input box
async function _sendChatSilent(text) {
  appendMsg(text, 'user');
  chatHistory.push({role:'user', content: text});
  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');
  try {
    const fetchPromise = fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: chatHistory})
    });
    const res = await fetchPromise;
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({role:'assistant', content: reply});
  } catch(e) {
    thinking.textContent = lang === 'zh' ? '连接失败，请运行 python -m selfos serve' : 'Connection failed — run python -m selfos serve';
  }
}

