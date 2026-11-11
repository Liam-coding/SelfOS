"""Evaluate the record boundary, not model extraction; no API or source scanning."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from selfos.knowledge.records import validate_record, merge_records


def evaluate(cases):
    rows=[]
    for case in cases:
        messages=[{'id':'m1','role':case.get('role','user'),'text':case['text'],
            'timestamp':'2026-11-12T10:00:00Z','provenance':case.get('provenance','')}]
        if case.get('context'):
            messages.append({'id':'m2','role':'assistant','text':case['context'],'timestamp':'2026-11-12T10:00:01Z'})
        record={'key':case['key'],'value':case['value'],'text':case['value'],
            'domain':case.get('domain','personal'),'kind':case.get('kind','user_fact'),
            'temporal':case.get('temporal','current'),'source_ids':case.get('source_ids',['m1']),
            'evidence':case.get('evidence',case['text'])}
        state={};traceable=False;error=False
        try:
            validated=validate_record(record,{'messages':messages})
            merge_records(state,'personal_facts',[validated],
                {'domains':case.get('domains',['personal','health']),'detail':'balanced'})
            traceable=all(any(m['id']==i for m in messages) for i in validated['source_ids']) and any(
                validated['evidence'] in m['text'] for m in messages if m['id'] in validated['source_ids'])
        except ValueError:
            error=True
        retained=bool(state.get('personal_facts'))
        rows.append({'id':case['id'],'expected_current':case['expected_current'],'retained_current':retained,
            'archived':bool(state.get('records_history')),'rejected_invalid':error,
            'structurally_traceable':traceable if retained else None})
    tp=sum(r['expected_current'] and r['retained_current'] for r in rows)
    fp=sum(not r['expected_current'] and r['retained_current'] for r in rows)
    fn=sum(r['expected_current'] and not r['retained_current'] for r in rows)
    retained=[r for r in rows if r['retained_current']]
    return {'scope':'record_validation_and_retention_only','model_calls':0,'cases':len(rows),
        'true_positive':tp,'false_positive':fp,'false_negative':fn,
        'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
        'structural_source_traceability':sum(r['structurally_traceable'] for r in retained)/len(retained) if retained else None,
        'rows':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,default=ROOT/'evals/personal_fact_holdout.json')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=evaluate(json.loads(args.cases.read_text(encoding='utf-8'))['cases'])
    text=json.dumps(report,indent=2)
    if args.output:args.output.write_text(text+'\n',encoding='utf-8')
    else:print(text)
