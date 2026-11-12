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
  updateChatLabel();
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

  const thinking = appendMsg('', 'ai');
  window.selfosI18n.bindText(thinking,'ui.chat.thinking');
  thinking.classList.add('thinking');

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({messages: chatHistory})
    });
    const data = await res.json();
    if(!res.ok||typeof data.reply!=='string'||!data.reply.trim())throw Error('chat_failed');
    thinking.remove();
    const reply = data.reply;
    appendMsg(reply, 'ai');
    chatHistory.push({role:'assistant', content: reply});
  } catch(e) {
    window.selfosI18n.bindText(thinking,'ui.chat.failed');
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

function updateChatLabel(){const button=document.getElementById('chat-collapse-btn');button.dataset.i18nAriaLabel=chatCollapsed?'ui.chat.expand':'ui.chat.collapse';button.setAttribute('aria-label',window.selfosI18n.t(button.dataset.i18nAriaLabel));}
document.addEventListener('selfos-language',updateChatLabel);
updateChatLabel();
