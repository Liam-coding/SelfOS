
// ── Theme ──
let isDark = localStorage.getItem('selfos-theme') === 'dark';
(function() {
  if (isDark) document.body.classList.add('dark');
  updateThemeBtn();
})();
function updateThemeBtn() {
  document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀';
}
function toggleTheme() {
  isDark = !isDark;
  document.body.classList.toggle('dark', isDark);
  localStorage.setItem('selfos-theme', isDark ? 'dark' : 'light');
  updateThemeBtn();
}

// ── Language ──
let lang = localStorage.getItem('selfos-lang') === 'zh' ? 'zh' : 'en';
document.documentElement.lang = lang;
function applyLanguage() {
  document.getElementById('lang-toggle').textContent = lang === 'zh' ? 'EN' : '中文';
  document.documentElement.lang = lang;
  localStorage.setItem('selfos-lang', lang);
  document.dispatchEvent(new Event('selfos-language'));
  updateKnowledgeOverview();
  document.querySelectorAll('[data-zh][data-en]').forEach(el => {
    el.textContent = el.dataset[lang];
  });
  const inp = document.getElementById('chat-input');
  inp.placeholder = lang === 'zh' ? '输入消息…' : 'Type a message…';
}
function toggleLang() {
  lang = lang === 'zh' ? 'en' : 'zh';
  applyLanguage();
}
document.addEventListener('DOMContentLoaded', applyLanguage);

