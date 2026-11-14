(function(window){
  'use strict';
  window.selfosUI.register('request',()=>{
    let nativeFetch=null,wrappedFetch=null,generation=0;
    return {
      request(...args){return window.fetch(...args);},
      init(){
        nativeFetch=window.fetch;const mountedGeneration=++generation;
        wrappedFetch=async(...args)=>{
          const response=await nativeFetch.apply(window,args);
          if(mountedGeneration===generation&&response.status===401&&!String(args[0]).includes('/auth/'))location.replace('/login');
          return response;
        };
        window.fetch=wrappedFetch;
      },
      teardown(){++generation;if(window.fetch===wrappedFetch)window.fetch=nativeFetch;}
    };
  },{dependencies:['locale']});
})(window);
