"""providers / client responsibilities."""
import io
import json
import time
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from selfos.providers.settings import load_config
from selfos.providers.settings import proxy_info

def adapt_request(request, config):
    body=json.loads(request.data)
    body['model']=config['model'] or body.get('model','claude-haiku-4-5-20251001')
    headers={'Content-Type':'application/json'}
    base=config['base_url'].rstrip('/')
    if config['provider']=='anthropic':
        endpoint=base+('/messages' if base.endswith('/v1') else '/v1/messages')
        headers.update({'x-api-key':config['api_key'],'anthropic-version':'2023-06-01'})
    else:
        endpoint=base+'/chat/completions'
        messages=body['messages']
        if body.get('system'): messages=[{'role':'system','content':body['system']}]+messages
        converted={'model':body['model'],'max_tokens':body['max_tokens'],'messages':messages}
        if body.get('tools'):
            converted['tools']=[{'type':'function','function':{'name':t['name'],'description':t.get('description',''),
                                 'parameters':t['input_schema']}} for t in body['tools']]
            choice=body.get('tool_choice',{})
            if choice.get('name'):
                converted['tool_choice']={'type':'function','function':{'name':choice['name']}}
                converted['parallel_tool_calls']=False
        body=converted
        if config['api_key']: headers['Authorization']='Bearer '+config['api_key']
    return Request(endpoint,data=json.dumps(body).encode('utf-8'),headers=headers,method='POST')


def normalize_response(data, provider):
    if provider=='anthropic': return data
    choice=data['choices'][0]; msg=choice['message']; content=[]
    if msg.get('content'): content.append({'type':'text','text':msg['content']})
    for t in msg.get('tool_calls') or []:
        f=t['function'];content.append({'type':'tool_use','name':f['name'],'input':json.loads(f['arguments'])})
    return {'content':content,'stop_reason':'max_tokens' if choice.get('finish_reason')=='length' else 'end_turn'}


def request_opener(root, budget=None):
    config=load_config(root)
    def open_request(request, timeout=90):
        req=adapt_request(request,config)
        ticket=None
        from selfos.storage.usage import current_request_usage
        effective_budget = current_request_usage() or budget
        try:
            opener=provider_opener(config,req.full_url)
            if effective_budget is not None:
                ticket=effective_budget.claim()
            with opener.open(req,timeout=timeout) as response: data=json.loads(response.read())
            if hasattr(effective_budget,'observe'):
                effective_budget.observe(ticket,data,config['provider'])
            return io.BytesIO(json.dumps(normalize_response(data,config['provider'])).encode())
        except Exception as error:
            if ticket is not None and hasattr(effective_budget,'fail'):
                effective_budget.fail(ticket)
            if isinstance(error,HTTPError):
                raise RuntimeError(f'Model API HTTP {error.code}; check authentication, endpoint and model') from None
            if isinstance(error,(URLError,OSError)):
                raise RuntimeError('Cannot connect to model API; check endpoint and proxy') from None
            raise
    return open_request


def test_connection(root):
    c=load_config(root)
    if not c['model']: raise ValueError('Choose a model before testing')
    schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
    body={'model':c['model'],'max_tokens':128,'messages':[{'role':'user','content':'Return ok=true through the connection_check tool.'}],
          'tools':[{'name':'connection_check','input_schema':schema}],'tool_choice':{'name':'connection_check','type':'tool'}}
    with request_opener(root)(Request(c['base_url'],data=json.dumps(body).encode()),timeout=20) as r: data=json.loads(r.read())
    calls=[b for b in data['content'] if b.get('type')=='tool_use' and b.get('name')=='connection_check']
    if len(calls)!=1 or calls[0]['input']!={'ok':True}: raise ValueError('Connected, but model did not return the required structured output')
    return {'ok':True,'message':'Network, authentication and structured output passed'}


def provider_opener(config, url):
    """Shared proxy routing and redirect protection for provider requests."""
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    proxies=dict(proxy_info(config)['proxies'])
    if proxies.get('all'):
        proxies.setdefault('http',proxies['all']); proxies.setdefault('https',proxies['all'])
    if urlsplit(url).hostname in ('localhost','127.0.0.1','::1'): proxies={}
    return build_opener(ProxyHandler(proxies),NoRedirect())


class ModelListUnsupported(RuntimeError):
    pass


def list_models(root, patch):
    """Read model metadata using a validated draft; never save or generate."""
    from selfos.providers.settings import resolve_config
    c=resolve_config(root,patch)
    base=c['base_url'].rstrip('/')
    endpoint=base+('/models' if c['provider']=='openai' or base.endswith('/v1') else '/v1/models')
    headers={'Accept':'application/json'}
    if c['provider']=='anthropic':
        headers.update({'x-api-key':c['api_key'],'anthropic-version':'2023-06-01'})
    elif c['api_key']: headers['Authorization']='Bearer '+c['api_key']
    try:
        models=[];cursor=None;seen=set();size=0;deadline=time.monotonic()+20
        opener=provider_opener(c,endpoint)
        for page in range(20):
            url=endpoint+('?' + urlencode({'after_id':cursor}) if cursor else '')
            req=Request(url,headers=headers,method='GET')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise RuntimeError('Model discovery timed out')
            with opener.open(req,timeout=remaining) as response:raw=response.read(1048577)
            size+=len(raw)
            if size>1048576: raise RuntimeError('Model list is too large')
            data=json.loads(raw)
            if not isinstance(data,dict) or not isinstance(data.get('data'),list):
                raise RuntimeError('Invalid model list')
            for item in data['data']:
                name=item.get('id') if isinstance(item,dict) else None
                if not isinstance(name,str) or not name.strip() or len(name)>4096 or any(ord(x)<32 for x in name):
                    raise RuntimeError('Invalid model identifier')
                models.append(name.strip())
            if c['provider']!='anthropic' or not data.get('has_more'):
                return {'models':sorted(set(models))}
            cursor=data.get('last_id')
            if not isinstance(cursor,str) or not cursor or len(cursor)>4096 or cursor in seen:
                raise RuntimeError('Invalid model pagination')
            seen.add(cursor)
        raise RuntimeError('Too many model pages')
    except HTTPError as error:
        if error.code in (404,405,501): raise ModelListUnsupported('Model discovery is unsupported') from None
        raise RuntimeError('Model discovery failed') from None
    except (URLError,OSError,ValueError):
        raise RuntimeError('Model discovery failed') from None
