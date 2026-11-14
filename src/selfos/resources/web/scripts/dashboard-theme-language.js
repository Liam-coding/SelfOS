(function(window){
'use strict';
window.selfosUI.register('theme',()=>{
let isDark=false,document=null;
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

function applyLanguage() {

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

function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node))return;if(node.id==='theme-toggle'&&node.dataset.selfosAction==='theme.toggle')toggleTheme();else if(node.id==='lang-toggle'&&node.dataset.selfosAction==='theme.language')toggleLang();}
return {toggle:toggleTheme,apply:applyLanguage,toggleLanguage:toggleLang,init(doc){document=doc;isDark=localStorage.getItem('selfos-theme')==='dark';if(isDark)document.body.classList.add('dark');updateThemeBtn();applyLanguage();document.addEventListener('selfos-language',applyLanguage);document.addEventListener('click',action);},teardown(){document.removeEventListener('selfos-language',applyLanguage);document.removeEventListener('click',action);document=null;}};
},{dependencies:['locale'],roots:['#theme-toggle','#lang-toggle']});
for(const [name,method]of Object.entries({toggleTheme:'toggle',toggleLang:'toggleLanguage',applyLanguage:'apply'})){if(!window[name])window[name]=(...args)=>window.selfosUI.module('theme')[method](...args);}
})(window);
