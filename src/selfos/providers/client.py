"""providers / client responsibilities."""
import io
import json
from urllib.request import Request, ProxyHandler, build_opener
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
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
        info=proxy_info(config); proxies=dict(info['proxies'])
        if proxies.get('all'):
            proxies.setdefault('http',proxies['all']);proxies.setdefault('https',proxies['all'])
        if urlsplit(req.full_url).hostname in ('localhost','127.0.0.1','::1'): proxies={}
        try:
            # Redirects must not forward API credentials to another origin.
            from urllib.request import HTTPRedirectHandler
            class NoRedirect(HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs): return None
            opener=build_opener(ProxyHandler(proxies),NoRedirect())
            if budget is not None:
                budget.claim()
            with opener.open(req,timeout=timeout) as response: data=json.loads(response.read())
            return io.BytesIO(json.dumps(normalize_response(data,config['provider'])).encode())
        except HTTPError as error: raise RuntimeError(f'Model API HTTP {error.code}; check authentication, endpoint and model') from None
        except (URLError,OSError): raise RuntimeError('Cannot connect to model API; check endpoint and proxy') from None
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
