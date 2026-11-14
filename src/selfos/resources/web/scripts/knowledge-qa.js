function createKnowledgeQA({el,on,requests}){
 let mode='knowledge',project='',epoch=0;const pending=new Set();
 const tr=key=>window.selfosI18n.t('qa.'+key);
 const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 const label=(tag,key,cls)=>{const n=node(tag,undefined,cls);window.selfosI18n.bindText(n,'qa.'+key);return n;};
 async function request(url,options={}){const controller=new AbortController();pending.add(controller);const owner=epoch;
  try{const response=await fetch(url,{...options,signal:controller.signal});const data=await response.json();if(owner!==epoch)throw Error('cancelled');if(!response.ok)throw Error(data.code||'qa_unavailable');return data;}
  finally{pending.delete(controller);}
 }
 function update(){el('chat-mode').value=mode;el('chat-project').disabled=mode!=='knowledge';el('chat-cancel').hidden=!requests.size;el('chat-input').maxLength=mode==='knowledge'?2000:10000;}
 function init(){
  let controls=el('chat-qa-controls');if(!controls){controls=node('div',undefined,'chat-qa-controls');controls.id='chat-qa-controls';
   const modeLabel=label('label','mode'),select=node('select');modeLabel.htmlFor='chat-mode';select.id='chat-mode';
   for(const value of ['knowledge','conversation']){const option=label('option',value);option.value=value;select.appendChild(option);}
   const projectLabel=label('label','project'),scope=node('select');projectLabel.htmlFor='chat-project';scope.id='chat-project';const all=label('option','all_projects');all.value='';scope.appendChild(all);
   const stop=label('button','cancel');stop.id='chat-cancel';stop.type='button';stop.dataset.selfosAction='chat.cancel';stop.hidden=true;
   controls.append(modeLabel,select,projectLabel,scope,stop);el('chat-panel').insertBefore(controls,el('chat-messages'));
  }
  on(el('chat-mode'),'change',()=>{mode=el('chat-mode').value;update();});on(el('chat-project'),'change',()=>{project=el('chat-project').value;});update();
  if(mode!=='knowledge')return;
  const owner=epoch;request('/__knowledge_qa_context__').then(data=>{if(owner!==epoch)return;const select=el('chat-project');select.replaceChildren();const all=label('option','all_projects');all.value='';select.appendChild(all);for(const item of data.projects||[]){const option=node('option',item.title);option.value=item.id;select.appendChild(option);}if([...select.options].some(option=>option.value===project))select.value=project;else project='';}).catch(()=>{});
 }
 function render(holder,data){holder.classList.add('qa-answer');holder.appendChild(label('p',data.answer_kind==='insufficient_evidence'?'insufficient':'interpretation','qa-label'));holder.appendChild(node('p',data.reply));
  for(const reference of data.references||[]){const card=node('section',undefined,'qa-reference');card.appendChild(node('h4',reference.title));
   card.appendChild(label('span',({user_fact:'kind_fact',inference:'kind_inference',user_correction:'kind_correction'})[reference.kind]||'kind_record','qa-label'));
   if(reference.category==='projects')card.appendChild(label('span','status_'+(['active','in_progress','blocked','planning','paused','ongoing','completed'].includes(reference.status)?reference.status:'unknown'),'qa-label'));
   for(const [condition,key]of [[reference.user_corrected,'correction'],[reference.historical,'history'],[reference.conflict,'conflict'],[!reference.verified,'unverified'],[reference.source_scope!=='record','context_scope']])if(condition)card.appendChild(label('span',key,'qa-label'));
   card.appendChild(node('p',reference.summary));if(reference.evidence){card.appendChild(label('p','original_quote','qa-label'));card.appendChild(node('blockquote',reference.evidence));}
   const detail=label('button','view_record');detail.type='button';detail.dataset.qaDetail=reference.id;card.appendChild(detail);
   on(detail,'click',async()=>{const owner=epoch;detail.disabled=true;try{await request('/__knowledge_qa_citation__?'+new URLSearchParams({record:reference.id,revision:reference.revision}));if(owner!==epoch)return;await window.selfosUI.module('knowledge').openDetail(reference.id,reference.revision);}catch(error){if(owner===epoch)card.appendChild(label('p','stale'));}finally{if(owner===epoch)detail.disabled=false;}});
   if(reference.source_coverage==='representative')card.appendChild(label('p','representative','qa-label'));
   for(const source of reference.sources||[]){const button=node('button',source.file);button.type='button';button.dataset.qaSource=source.id;card.appendChild(button);
    on(button,'click',async()=>{const owner=epoch;button.disabled=true;try{await request('/__knowledge_qa_citation__?'+new URLSearchParams({record:reference.id,revision:reference.revision}));if(owner!==epoch)return;const knowledge=window.selfosUI.module('knowledge');await knowledge.openDetail(reference.id,reference.revision);if(owner!==epoch)return;await knowledge.readSource(source.id);}catch(error){if(owner===epoch)card.appendChild(label('p','stale'));}finally{if(owner===epoch)button.disabled=false;}});
   }
   holder.appendChild(card);
  }
  for(const inference of data.inferences||[]){const section=node('section',undefined,'qa-inference');section.appendChild(label('p','inference','qa-label'));section.appendChild(node('p',inference.text));section.appendChild(label('p','basis','qa-label'));section.appendChild(node('p',(data.references||[]).filter(reference=>inference.record_ids.includes(reference.id)).map(reference=>reference.title).join(', ')));holder.appendChild(section);}
 }
 function teardown(){++epoch;project=el('chat-project')?.value||project;for(const controller of pending)controller.abort();pending.clear();}
 return {init,render,update,teardown,mode:()=>mode,project:()=>el('chat-project')?.value||project,setMode:value=>{if(['knowledge','conversation'].includes(value)){mode=value;if(el('chat-mode'))update();}},tr};
}
