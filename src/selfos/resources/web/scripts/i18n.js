(() => {
  if(window.selfosI18n)return;
  const catalogs=__I18N_CATALOGS__,locales=catalogs.locales,english=locales.en.messages,aliases=new Map(),bindings=new Map();
  for(const [id,locale]of Object.entries(locales))for(const alias of [id,...locale.aliases])aliases.set(alias.toLowerCase(),id);
  const resolve=value=>typeof value==='string'?(aliases.get(value.toLowerCase())||'en'):'en';
  let preference;
  try{preference=localStorage.getItem('selfos-lang');}catch(error){}
  let locale=resolve(preference);
  function formatter(kind,options){try{return new Intl[kind](locales[locale].tag,options);}catch(error){return new Intl[kind]('en',options);}}
  const number=(value,options={})=>typeof value==='number'&&Number.isFinite(value)?formatter('NumberFormat',options).format(value):String(value);
  function t(key,params={}){
    if(typeof params==='function')params=params();
    const message=locales[locale].messages[key]??english[key]??english['ui.common.unavailable']??'';
    return message.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g,(_,key)=>{if(!Object.prototype.hasOwnProperty.call(params,key))throw Error('Missing translation parameter: '+key);return typeof params[key]==='number'?number(params[key]):String(params[key]);});
  }
  function date(value,options={}){
    if(typeof value!=='string')return t('ui.common.unknown');
    const dateOnly=/^\d{4}-\d{2}-\d{2}$/.test(value);
    if(!dateOnly&&!/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value))return t('ui.common.unknown');
    const calendar=value.slice(0,10),calendarDate=new Date(calendar+'T00:00:00Z');
    if(!Number.isFinite(calendarDate.getTime())||calendarDate.toISOString().slice(0,10)!==calendar)return t('ui.common.unknown');
    const parsed=new Date(dateOnly?value+'T00:00:00Z':value);
    if(!Number.isFinite(parsed.getTime())||(dateOnly&&parsed.toISOString().slice(0,10)!==value))return t('ui.common.unknown');
    const format={dateStyle:'medium',...options};
    if(dateOnly){delete format.timeStyle;delete format.hour;delete format.minute;delete format.second;delete format.fractionalSecondDigits;delete format.dayPeriod;format.timeZone='UTC';}
    return formatter('DateTimeFormat',format).format(parsed);
  }
  function displayText(key,params={}){try{return t(key,params);}catch(error){return t('ui.common.unavailable');}}
  function bindText(element,key,params={}){if(typeof element==='string')element=document.getElementById(element);if(!element)return;bindings.set(element,{key,params});element.textContent=displayText(key,params);}
  function translate(){
    document.documentElement.lang=locales[locale].document_tag;
    for(const element of document.querySelectorAll('[data-i18n],[data-i18n-placeholder],[data-i18n-title],[data-i18n-aria-label]')){
      let params={};try{params=JSON.parse(element.dataset.i18nParams||'{}');}catch(error){}
      if(element.dataset.i18n)element.textContent=displayText(element.dataset.i18n,params);
      for(const [field,attribute]of [['i18nPlaceholder','placeholder'],['i18nTitle','title'],['i18nAriaLabel','aria-label']])if(element.dataset[field])element.setAttribute(attribute,displayText(element.dataset[field],params));
    }
    for(const element of document.querySelectorAll('[data-zh][data-en]')){if(element.dataset.en!==undefined&&element.dataset.zh!==undefined)element.textContent=element.dataset[locales[locale].document_tag]??element.dataset.en;}
    for(const [element,state]of bindings){if(element.isConnected===false){bindings.delete(element);continue;}element.textContent=displayText(state.key,state.params);}
  }
  function setLocale(value){locale=resolve(value);try{localStorage.setItem('selfos-lang',locale);}catch(error){}translate();document.dispatchEvent(new Event('selfos-language'));}
  function populateLanguageSelect(element){if(typeof element==='string')element=document.getElementById(element);if(!element)return;const value=locale;element.replaceChildren();for(const [id,data]of Object.entries(locales)){const option=document.createElement('option');option.value=id;option.textContent=data.name;element.append(option);}element.value=value;}
  window.selfosI18n={has:key=>Object.prototype.hasOwnProperty.call(english,key),get locales(){return Object.fromEntries(Object.entries(locales).map(([id,data])=>[id,{name:data.name}]));},get locale(){return locale;},get tag(){return locales[locale].tag;},get documentTag(){return locales[locale].document_tag;},t,number,date,translate,bindText,setLocale,populateLanguageSelect};
  document.documentElement.lang=locales[locale].document_tag;
  document.addEventListener('DOMContentLoaded',translate);
})();
