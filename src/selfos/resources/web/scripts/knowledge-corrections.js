(() => {
 const tr=(key,values={})=>window.selfosI18n.t('search.'+key,values);
 const label=(element,key,values={})=>{window.selfosI18n.bindText(element,'ui.common.value',()=>({value:tr(key,values)}));return element;};
 const node=(tag,key,cls)=>{const n=document.createElement(tag);if(key)label(n,key);if(cls)n.className=cls;return n;};
 const button=(key,attribute,callback)=>{const n=node('button',key,'kb-source');n.type='button';if(attribute)n.setAttribute('data-correction-'+attribute,'');n.onclick=callback;return n;};
 const mutate=async payload=>{
   payload.request_id ||= crypto.randomUUID();
   document.getElementById('kb-correction-history')?.querySelectorAll('button').forEach(b=>b.disabled=true);
   let response,data;
   try{response=await fetch('/__knowledge_correct__',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});data=await response.json();}
   catch(error){throw {code:'correction_unavailable'};}
   if(!response.ok)throw {code:data.code||'correction_unavailable'};
   return data;
 };
 function mount(holder,data,onSaved){
   if(window.selfosReadOnlyDemo||!data.corrections?.editable)return;
   const item=data.item,options=data.corrections,section=node('section',null,'kc-controls'),toolbar=node('div',null,'kc-toolbar'),body=node('div'),status=node('p');
   status.setAttribute('role','status');section.append(node('h3','correction_heading'),node('p','correction_notice','kb-meta'),toolbar,body,status);holder.append(section);
   let pending=false,retryBody='',retryId='';
   const save=async payload=>{
     if(pending)return;pending=true;section.setAttribute('aria-busy','true');section.querySelectorAll('button').forEach(b=>b.disabled=true);label(status,'correction_saving');
     const body=JSON.stringify(payload);if(body!==retryBody){retryBody=body;retryId=crypto.randomUUID();}payload.request_id=retryId;
     try{await mutate(payload);await onSaved();}
     catch(error){label(status,'error_'+error.code);}
     finally{pending=false;section.removeAttribute('aria-busy');section.querySelectorAll('button').forEach(b=>b.disabled=false);}
   };
   const openForm=merge=>{
     body.replaceChildren();const form=node('form',null,'kc-form');
     const field=(key,tag,value,attribute)=>{const wrap=node('label');wrap.append(node('span',key));const input=node(tag);input.value=value;input.maxLength=2000;input.required=true;input.setAttribute('data-correction-'+attribute,'');if(tag==='textarea')input.rows=3;wrap.append(input);form.append(wrap);return input;};
     let value=null;
     if(['personal_facts','preferences'].includes(item.category))value=field('correction_value','input',options.value,'value');
     const text=field('correction_text','textarea',options.text,'text');let candidates=null;
     if(merge){const wrap=node('label');wrap.append(node('span','correction_merge_select'));candidates=node('select');candidates.multiple=true;candidates.required=true;candidates.setAttribute('data-correction-candidates','');
       for(const candidate of options.compatible){const option=node('option');option.value=candidate.id;option.textContent=candidate.title;candidates.append(option);}wrap.append(candidates);form.append(wrap);}
     const submit=node('button',merge?'correction_confirm_merge':'correction_save','kb-source');submit.type='submit';submit.setAttribute('data-correction-save','');
     form.append(submit,button('correction_cancel',null,()=>{body.replaceChildren();toolbar.querySelector('button')?.focus();}));
     form.onsubmit=event=>{event.preventDefault();const ids=[item.id,...(candidates?Array.from(candidates.selectedOptions,o=>o.value):[])];
       if(merge&&ids.length<2){label(status,'correction_choose_merge');return;}
       const patch={text:text.value};if(value)patch.value=value.value;save({action:merge?'merge':'edit',ids,patch});};
     body.append(form);(value||text).focus();
   };
   toolbar.append(button('correction_edit','edit',()=>openForm(false)),button('correction_delete','delete',()=>{
     body.replaceChildren(node('p','correction_delete_notice'));
     const confirm=button('correction_confirm_delete','confirm-delete',()=>save({action:'delete',ids:[item.id]}));
     body.append(confirm,button('correction_cancel',null,()=>{body.replaceChildren();toolbar.querySelector('button')?.focus();}));confirm.focus();
   }));
   if(options.compatible?.length)toolbar.append(button('correction_merge','merge',()=>openForm(true)));
 }
 let historyGeneration=0;
 function originalDetails(originals){
   const details=node('details');details.append(node('summary','correction_originals'));
   for(const original of originals||[]){const description=node('p');description.textContent=original.text||original.value;details.append(description);
     if(original.evidence){const quote=node('pre');quote.textContent=original.evidence;details.append(quote);}
     for(const identity of original.source_ids||[]){let offset=0,text='';const holder=node('div'),content=node('pre');content.hidden=true;
       const read=button('read_source','source',async()=>{read.disabled=true;
         try{const response=await fetch('/__knowledge_source__?'+new URLSearchParams({id:identity,offset,limit:24000}));const data=await response.json();if(!response.ok)throw {code:data.code||'unavailable'};
           text+=data.text;content.textContent=text;content.hidden=false;offset=data.next_offset??null;if(offset===null)read.hidden=true;else label(read,'more_source_text');
         }catch(error){holder.append(node('p','error_'+(error.code||'unavailable')));}finally{read.disabled=false;}
       });holder.append(read,content);details.append(holder);}
   }
   return details;
 }
 async function history(holder,onSaved){
   if(window.selfosReadOnlyDemo)return;
   const generation=++historyGeneration;holder.querySelectorAll('button').forEach(b=>b.disabled=true);
   try{
     const response=await fetch('/__knowledge_corrections__',{cache:'no-store'});if(!response.ok)return;const data=await response.json();
     if(generation!==historyGeneration)return;
     holder.replaceChildren();holder.hidden=!data.actions?.length;if(holder.hidden)return;holder.append(node('h3','correction_recent'));
     for(const action of data.actions.slice(-20).reverse()){
       const row=node('div',null,'kc-history-row'),title=node('span');title.textContent=action.title;row.append(title,node('span','correction_action_'+action.action));
       if(action.active){const payload={action:'undo',action_id:action.id};const undo=button('correction_undo','undo',async()=>{
         undo.disabled=true;try{await mutate(payload);await onSaved();}catch(error){row.append(node('p','error_'+error.code));undo.disabled=false;}
       });undo.disabled=!action.can_undo;row.append(undo);if(!action.can_undo)row.append(node('span','correction_dependency_note'));}
       else row.append(node('span','correction_undone'));row.append(originalDetails(action.originals));holder.append(row);
     }
   }catch(error){if(generation===historyGeneration)holder.hidden=true;}
 }
 window.selfosCorrections={mount,history};
})();
