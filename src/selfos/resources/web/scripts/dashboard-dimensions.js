(function(window){'use strict';window.selfosUI.register('dimensions',()=>{
// ── Dim icons ──
const DIM_ICONS = {
  career:'💼', work:'🛠', health:'💪', learning:'📚',
  research:'🔬', life:'🌿', family:'🏠'
};
let _currentDimKey = '';

function chatAboutDim() {
  document.getElementById('dim-modal').classList.remove('open');
  window.selfosUI.module('chat').open();
  return window.selfosUI.module('chat').send(window.selfosI18n.t('ui.dimension.discuss',{label:window.selfosI18n.t('ui.dimension.'+_currentDimKey)}));
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

function close(){document.getElementById('dim-modal').classList.remove('open');}
function backdrop(event){if(event.target===event.currentTarget)close();}
function action(event){const node=event.target.closest?.('[data-selfos-action]');if(!node||!document.contains(node))return;const actions={'dimensions.open':()=>{if(node.closest('.grid'))openDim(node);},'dimensions.discuss':()=>{if(node.closest('#dim-modal'))chatAboutDim();}};if(!Object.hasOwn(actions,node.dataset.selfosAction))return;event.preventDefault();actions[node.dataset.selfosAction]();}
function init(){document.addEventListener('click',action);document.getElementById('dim-modal').addEventListener('click',backdrop);}
function teardown(){document.removeEventListener('click',action);document.getElementById('dim-modal').removeEventListener('click',backdrop);}
return {open:openDim,discuss:chatAboutDim,close,init,teardown};
},{dependencies:['chat','locale'],roots:['#dim-modal','.grid']});
for(const [name,method]of Object.entries({openDim:'open',chatAboutDim:'discuss'}))if(!window[name])window[name]=(...args)=>window.selfosUI.module('dimensions')[method](...args);
})(window);
