// ── Chat collapse ──
let chatCollapsed = localStorage.getItem('selfos-chat-open') !== 'true';
document.getElementById('chat-panel').classList.toggle('collapsed', chatCollapsed);
document.getElementById('chat-collapse-btn').setAttribute('aria-expanded', String(!chatCollapsed));
function toggleChat(e) {
  if (e) e.stopPropagation();
  chatCollapsed = !chatCollapsed;
  document.getElementById('chat-panel').classList.toggle('collapsed', chatCollapsed);
  localStorage.setItem('selfos-chat-open', String(!chatCollapsed));
  document.getElementById('chat-collapse-btn').setAttribute('aria-expanded', String(!chatCollapsed));
  document.getElementById('chat-collapse-btn').setAttribute('aria-label', chatCollapsed ? '展开聊天' : '收起聊天');
}

// ── Chat ──
const chatHistory = [];
function appendMsg(text, role) {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'msg-user' : 'msg-ai');
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}
async function sendChat() {
  const inp = document.getElementById('chat-input');
  const text = inp.value.trim();
  if (!text) return;
  inp.value = '';
  inp.style.height = 'auto';
  document.getElementById('chat-send').disabled = true;

  appendMsg(text, 'user');
  chatHistory.push({role:'user', content: text});

  const thinking = appendMsg(lang === 'zh' ? '思考中…' : 'Thinking…', 'ai');
  thinking.classList.add('thinking');

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: chatHistory})
    });
    const data = await res.json();
    thinking.remove();
    const reply = data.reply || data.error || 'Error';
    appendMsg(reply, 'ai');
    chatHistory.push({role:'assistant', content: reply});
  } catch(e) {
    thinking.textContent = lang === 'zh' ? '连接失败，请运行 python -m selfos serve' : 'Connection failed — run python -m selfos serve';
    thinking.classList.add('thinking');
  }
  document.getElementById('chat-send').disabled = false;
  inp.focus();
}
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});
document.getElementById('chat-input').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 80) + 'px';
});

