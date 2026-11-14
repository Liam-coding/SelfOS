(function(window,document){
  'use strict';
  if(window.selfosUIBootstrapVersion){
    if(window.selfosUIBootstrapVersion!==1)throw new Error('Incompatible browser bootstrap version');
    return;
  }
  window.selfosUIBootstrapVersion=1;
  window.selfosUI.register('locale',()=>window.selfosI18n);
  const init=()=>window.selfosUI.init(document);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})(window,document);
