"""Offline supplied-candidate and merge-sequence evaluation; not model quality."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from selfos.knowledge.records import validate_record, merge_records


def ingest(state,value,index=0):
    identity='m'+str(index*2+1)
    messages=[{'id':identity,'role':value.get('role','user'),'text':value['text'],
        'timestamp':value.get('at','2026-11-12T10:00:00Z'),'provenance':value.get('provenance','')}]
    if value.get('context'):
        messages.append({'id':'m'+str(index*2+2),'role':value.get('context_role','assistant'),
            'text':value['context'],'timestamp':messages[0]['timestamp']})
    record={'key':value.get('key','communication.detail'),'value':value['value'],'text':value['value'],
        'kind':value.get('kind','user_fact'),'temporal':value.get('temporal','current'),'domain':'personal',
        'scope':value.get('scope','global'),'source_ids':value.get('source_ids',[identity]),
        'evidence':value.get('evidence',value['text'])}
    validated=validate_record(record,{'messages':messages})
    merge_records(state,'preferences',[validated],{'domains':value.get('domains',['personal']),'detail':'balanced'})
    known={m['id']:m for m in messages}
    traceable=all(i in known for i in validated['source_ids']) and any(
        validated['evidence'] in known[i]['text'] for i in validated['source_ids'])
    return validated,traceable


def evaluate(data):
    rows=[]
    for case in data['candidates']:
        state={};rejected=False;traceable=False
        try:_,traceable=ingest(state,case)
        except ValueError:rejected=True
        retained=bool(state.get('preferences'))
        rows.append({'id':case['id'],'expected':case['expected'],'retained':retained,
            'archived':bool(state.get('records_history')),'rejected_invalid':rejected,
            'structurally_traceable':traceable if retained else None})
    tp=sum(r['expected'] and r['retained'] for r in rows)
    fp=sum(not r['expected'] and r['retained'] for r in rows)
    fn=sum(r['expected'] and not r['retained'] for r in rows)
    sequences=[]
    for case in data['sequences']:
        state={}
        for index,value in enumerate(case['records']):ingest(state,value,index)
        current=sorted([r.get('scope','global'),r['value']] for r in state.get('preferences',[]))
        history=[r['value'] for r in state.get('records_history',[])]
        support=sum(len(r['source_ids']) for r in state.get('preferences',[]))
        matched=current==sorted(case['expected_current']) and all(v in history for v in case.get('expected_history',[]))
        if 'expected_support' in case:matched=matched and support==case['expected_support']
        sequences.append({'id':case['id'],'passed':matched,'current':current,'history':history,'support_count':support})
    retained=[r for r in rows if r['retained']]
    return {'scope':'record_validation_retention_and_merge_only','model_calls':0,
        'candidate_cases':len(rows),'true_positive':tp,'false_positive':fp,'false_negative':fn,
        'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
        'structural_source_traceability':sum(r['structurally_traceable'] for r in retained)/len(retained) if retained else None,
        'sequence_cases':len(sequences),'sequence_passes':sum(s['passed'] for s in sequences),
        'candidates':rows,'sequences':sequences}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,default=ROOT/'evals/preference_holdout.json')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=json.dumps(evaluate(json.loads(args.cases.read_text(encoding='utf-8'))),indent=2)
    if args.output:args.output.write_text(result+'\n',encoding='utf-8')
    else:print(result)
