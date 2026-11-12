"""Investigate canonical/staging visibility with actual local transaction logic."""
import json

from selfos.app.knowledge import get_status, run_knowledge
from selfos.knowledge.settings import VERSION, DEFAULT_SETTINGS, policy_hash


def test_stopped_import_keeps_personal_facts_staged_until_successful_resume(tmp_path):
    source=tmp_path/'source.jsonl'
    source.write_text(json.dumps({'type':'user','sessionId':'fact-fixture','cwd':str(tmp_path/'project'),
        'timestamp':'2026-11-12T10:00:00Z','message':{'content':'I work as a product designer.'}})+'\n')
    original=source.read_bytes()
    vault=tmp_path/'vault';vault.mkdir()
    canonical=vault/'.knowledge_pipeline.json'
    canonical.write_text(json.dumps({'cache':{},'cards':{},'lessons':[],'sources':{},'summaries':{},
        'schema_version':VERSION,'policy':DEFAULT_SETTINGS,'policy_hash':policy_hash(DEFAULT_SETTINGS)}))
    before=canonical.read_bytes()
    stop=False
    def progress(line):
        nonlocal stop
        if line.startswith('Saved session '):stop=True
    def summarize(item):
        message=item['messages'][0]
        return {'project':None,'lessons':[],'preferences':[],'history':[],
            'personal_facts':[{'key':'employment.role','value':'product designer',
                'text':'Works as a product designer.','domain':'personal','kind':'user_fact',
                'source_ids':[message['id']],'evidence':message['text'],'temporal':'current'}]}
    def no_refinement(_):raise AssertionError('A fact-only session needs no project refinement')
    stopped=run_knowledge(vault,roots=[source],summarize=summarize,refine=no_refinement,
        cancel=lambda:stop,progress=progress,max_workers=1)
    assert stopped['status']=='stopped' and not stopped['installed']
    assert canonical.read_bytes()==before
    assert get_status(vault)['counts']['personal_facts']==0
    stages=list((vault/'.knowledge_rebuild').glob('*/.knowledge_pipeline.json'))
    assert len(stages)==1
    assert len(json.loads(stages[0].read_text())['personal_facts'])==1
    def no_model(_):raise AssertionError('Resume must reuse the saved validated fixture summary')
    resumed=run_knowledge(vault,roots=[source],summarize=no_model,refine=no_refinement,max_workers=1)
    assert resumed['status']=='completed' and resumed['installed'] and resumed['model_calls']==0
    assert get_status(vault)['counts']['personal_facts']==1
    assert source.read_bytes()==original
