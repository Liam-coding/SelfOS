(function(window) {
  'use strict';
  const version=1;
  if(window.selfosUI) {
    if(window.selfosUI.version!==version)throw new Error('Incompatible selfosUI version');
    return;
  }
  const registrations=new Map();
  let mountedDocument=null, mounted=[];
  function register(id,factory,options={}) {
    if(typeof id!=='string'||!id||typeof factory!=='function')throw new Error('Invalid browser module');
    const moduleVersion=options.version===undefined?1:options.version;
    const existing=registrations.get(id);
    if(existing) {
      if(existing.version!==moduleVersion)throw new Error('Incompatible module version: '+id);
      return;
    }
    if(mountedDocument)throw new Error('Register browser modules before initialization');
    registrations.set(id,{factory,version:moduleVersion,dependencies:[...(options.dependencies||[])],roots:[...(options.roots||[])],nodes:[],api:null});
  }
  function ordered() {
    const result=[],visiting=new Set(),visited=new Set();
    function visit(id) {
      if(visited.has(id))return;
      if(visiting.has(id))throw new Error('Cyclic browser dependency: '+id);
      const entry=registrations.get(id);
      if(!entry)throw new Error('Missing browser dependency: '+id);
      visiting.add(id);entry.dependencies.forEach(visit);visiting.delete(id);visited.add(id);result.push(entry);
    }
    registrations.forEach((_,id)=>visit(id));return result;
  }
  function teardown() {
    const cleanup=mounted.slice().reverse();mounted=[];mountedDocument=null;
    let error;
    for(const entry of cleanup)try{entry.api.teardown?.();}catch(cause){error=error||cause;}
    if(error)throw error;
  }
  function init(document) {
    if(mountedDocument===document){
      for(const entry of mounted)if(entry.roots.some((selector,index)=>(document.querySelector?.(selector)||null)!==entry.nodes[index]))throw new Error('Browser module remount-required'+(entry.api.busy?.()?' (busy)':'')+': '+entry.roots.join(','));
      return;
    }
    if(mountedDocument)throw new Error('Browser modules require teardown before remount');
    const entries=ordered();
    for(const entry of entries)if(!entry.api)entry.api=entry.factory(window.selfosUI);
    mountedDocument=document;
    try {
      for(const entry of entries) {mounted.push(entry);entry.api.init?.(document);entry.nodes=entry.roots.map(selector=>document.querySelector?.(selector)||null);}
    }catch(error) {try{teardown();}catch(_){}throw error;}
  }
  function module(id) {
    const entry=registrations.get(id);
    if(!entry)throw new Error('Unknown browser module: '+id);
    if(!entry.api)entry.api=entry.factory(window.selfosUI);
    return entry.api;
  }
  window.selfosUI=Object.freeze({version,register,init,module,teardown});
})(window);
