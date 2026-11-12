"""Synthetic profiles and a loopback model for optional browser validation."""
import copy
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def create_profile(root):
    from selfos.sources.conversations import extract_conversations
    vault=root/'vault'; vault.mkdir(exist_ok=True)
    sources=root/'fixture-sources'; sources.mkdir()
    (sources/'.selfos-integration-source').touch()
    for index in range(2):
        rows=[{'type':'session_meta','payload':{'id':f'integration-{index}','cwd':f'C:/synthetic/integration-{index}'}},
              {'type':'response_item','timestamp':f'2026-01-0{index+1}T10:00:00Z',
               'payload':{'type':'message','role':'user','content':[{'type':'input_text',
                 'text':f'We are building Fixture Project {index}. Our goal is reliable checkpointed knowledge import. Use atomic backups and inspect source provenance.'}]}}]
        (sources/f'{index}.jsonl').write_text(chr(10).join(json.dumps(row) for row in rows),encoding='utf-8')
    messages=extract_conversations([sources]); message=messages[0]
    ui_sources=root/'ui-sources';ui_sources.mkdir()
    (ui_sources/'claude.jsonl').write_text(json.dumps({'type':'user','sessionId':'ui-only',
        'cwd':'C:/synthetic/ui','timestamp':'2026-01-01T10:00:00Z',
        'message':{'content':'Fixture Claude source for source-filter exclusion.'}}),encoding='utf-8')
    ui_message=extract_conversations([ui_sources])[0]
    identity=message['project_id']
    card={'project_id':identity,'title':'Fixture Search Project','intent':'Fixture reliable import',
          'domain':'work','status':'blocked','blockers':['Fixture missing adapter'],'next_steps':['Fixture validate recovery'],
          'decisions':['Fixture use checkpoints'],'verified':False,'source_ids':[message['id']],
          'updated_at':message['timestamp'],'decision_records':[],'state_inputs':[]}
    for index in range(45):
        date=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=index)).isoformat()
        card['decision_records'].append({'text':f'Fixture decision {index:02}: retain source links',
            'source_ids':[message['id']],'observed_at':date,'domain':'work','source_scope':'session_context'})
        card['state_inputs'].append({'status':'blocked' if index%2 else 'in_progress','blockers':[f'Fixture blocker {index}'],
            'next_steps':[f'Fixture next step {index}'],'verified':False,'source_ids':[message['id']],
            'observed_at':date,'domain':'work','source_scope':'session_context','_order':[date,index]})
    lessons=[{'text':f'Fixture lesson {index:02}: validate assumptions before changing an interface.',
              'kind':'inference','domain':'work','source_ids':[message['id']],
              'observed_at':message['timestamp']} for index in range(60)]
    lessons.append({'text':'Fixture lesson 07: distinct Claude source candidate.','kind':'inference',
        'domain':'work','source_ids':[ui_message['id']],'observed_at':ui_message['timestamp']})
    state={'cards':{identity:card},'lessons':lessons,'sources':{m['id']:m for m in [*messages,ui_message]},
           'preferences':[],'personal_facts':[],'summaries':{},'cache':{}}
    (vault/'.knowledge_pipeline.json').write_text(json.dumps(state),encoding='utf-8')
    (vault/'PROFILE.md').write_text('- Preferred name: Fixture User',encoding='utf-8')
    return {'vault':vault,'source_root':sources,'ui_sources':ui_sources,
            'original_bytes':{p:p.read_bytes() for folder in (sources,ui_sources) for p in folder.glob('*.jsonl')}}


class ModelFixture:
    def __init__(self):
        self.requests=[]; self.gate=threading.Event(); self.blocked=threading.Event()
        self.gate.set(); self.extractions=0; self.block_second=False; self.fail_test=False; self.extraction_sessions=[]

    def __enter__(self):
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path!='/v1/chat/completions':
                    self.send_error(404); return
                if self.headers.get('Authorization')!='Bearer synthetic-fixture-key':
                    self.send_error(401,'Only the synthetic fixture key is accepted'); return
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append(copy.deepcopy(body))
                tools=body.get('tools',[])
                if not tools:
                    if fixture.fail_test:
                        self.send_error(503,'Synthetic connection failure'); return
                    message={'role':'assistant','content':'Fixture model connection passed.'}
                else:
                    name=tools[0]['function']['name']
                    prompt=json.loads(body['messages'][-1]['content']) if name!='connection_check' else {}
                    if name=='connection_check':
                        if fixture.fail_test:
                            self.send_error(503,'Synthetic connection failure'); return
                        result={'ok':True}
                    elif name=='retain_knowledge':
                        fixture.extractions+=1
                        fixture.extraction_sessions.append(tuple(m['timestamp'] for m in prompt['conversations']))
                        if fixture.block_second and fixture.extractions==2:
                            fixture.blocked.set()
                            if not fixture.gate.wait(35):
                                self.send_error(504,'Fixture gate timeout'); return
                        conversations=prompt['conversations']
                        card={'project_id':'current-project','title':'Fixture imported project',
                              'intent':'Build reliable checkpointed knowledge import','domain':'work',
                              'status':'in_progress','decisions':['Use atomic backups'], 'blockers':[],
                              'next_steps':['Inspect source provenance'],'source_ids':[m['id'] for m in conversations],
                              'updated_at':max(m['timestamp'] for m in conversations),'verified':False}
                        result={'project':card,'lessons':[],'personal_facts':[],'preferences':[],'history':[]}
                    elif name=='synthesize_knowledge':
                        result={'project':prompt['project'],'lessons':[],'observations':[]}
                    else:
                        self.send_error(400,'Unexpected fixture tool'); return
                    message={'role':'assistant','content':None,'tool_calls':[{'id':'fixture-call','type':'function',
                        'function':{'name':name,'arguments':json.dumps(result)}}]}
                content=json.dumps({'choices':[{'finish_reason':'stop','message':message}]}).encode()
                self.send_response(200); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.base_url=f'http://127.0.0.1:{self.server.server_port}/v1'
        return self

    def __exit__(self,*args):
        self.gate.set(); self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
