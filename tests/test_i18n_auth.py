import shutil,subprocess
from selfos.web.i18n import runtime
from selfos.web.rendering.resources import frontend_text


def test_auth_unknown_error_and_invalid_json_keep_status_and_localized_binding(tmp_path):
    common=runtime().split('<script',1)[1].split('>',1)[1].split('</script>',1)[0]
    auth=frontend_text('scripts/ui-runtime.js')+frontend_text('scripts/auth-common.js')
    harness=r"""
const status={textContent:'',isConnected:true};global.window=global;global.localStorage={getItem:()=>null,setItem(){}};global.document={documentElement:{lang:'en'},getElementById:()=>status,querySelectorAll:()=>[],addEventListener(){},dispatchEvent(){}};
COMMON
AUTH
(async()=>{
global.fetch=async()=>({ok:false,status:401,json:async()=>({error_code:'unknown-new-code'})});
try{await authRequest('/auth/login',{});throw Error('Request should fail');}catch(error){if(error.status!==401||error.code!=='auth_error')throw Error('Unknown authentication error lost fallback/status');authStatus(status,error.code);}
const english=status.textContent;selfosI18n.setLocale('zh');if(status.textContent===english)throw Error('Authentication error binding stale');
global.fetch=async()=>({ok:false,status:502,json:async()=>{throw Error('Invalid JSON');}});
try{await authRequest('/auth/login',{});throw Error('Request should fail');}catch(error){if(error.status!==502||error.code!=='auth_error')throw Error('Invalid JSON lost HTTP status');}
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    path=tmp_path/'auth.js';path.write_text(harness.replace('COMMON',common).replace('AUTH',auth),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(path)],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
