
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
let lang = window.selfosI18n.documentTag;
function applyLanguage() {
 lang=window.selfosI18n.documentTag;
 window.selfosI18n.translate();
 const recordedDate=document.getElementById('overall-date');
 if(recordedDate&&recordedDate.dataset.date)window.selfosI18n.bindText(recordedDate,'ui.dashboard.updated',()=>({date:window.selfosI18n.date(recordedDate.dataset.date)}));
 const button=document.getElementById('lang-toggle');
 if(button)button.textContent=window.selfosI18n.locale;
}
function toggleLang() {
 const ids=Object.keys(window.selfosI18n.locales);
 window.selfosI18n.setLocale(ids[(ids.indexOf(window.selfosI18n.locale)+1)%ids.length]);
}
document.addEventListener('selfos-language',applyLanguage);
document.addEventListener('DOMContentLoaded',applyLanguage);
