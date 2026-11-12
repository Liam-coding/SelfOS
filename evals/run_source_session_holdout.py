"""Score separately labeled source sessions; offline unless model calls are explicit."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from selfos.knowledge.identity import normalized
from selfos.knowledge.projects import validate_summary


def prepare(case):
    messages=[{'id':case['id']+'-user','role':'user','text':case['text'],
               'timestamp':'2026-03-04T10:00:00Z','project':'Synthetic evaluation',
               'project_id':'evaluation-project','provenance':case.get('provenance','')}]
    if case.get('context'):
        messages.append({'id':case['id']+'-assistant','role':'assistant','text':case['context'],
                         'timestamp':'2026-03-04T10:01:00Z','project':'Synthetic evaluation',
                         'project_id':'evaluation-project'})
    return {'project_id':'evaluation-project','session_id':case['id'],'messages':messages}


def score(data,predictions):
    tp=fp=fn=temporary_fp=traceable=retained=invalid=0
    rows=[]
    for case in data['cases']:
        raw=predictions.get(case['id'])
        if raw is None:
            rows.append({'id':case['id'],'missing_prediction':True})
            fn+=len(case['expected']);continue
        if isinstance(raw,dict) and raw.get('_evaluation_error'):
            invalid+=1;fn+=len(case['expected'])
            rows.append({'id':case['id'],'invalid_output':raw['_evaluation_error']});continue
        try:result=validate_summary(raw,prepare(case))
        except (ValueError,TypeError) as error:
            invalid+=1
            rows.append({'id':case['id'],'invalid_output':str(error)})
            fn+=len(case['expected']);continue
        actual=[(category,record) for category in ('personal_facts','preferences')
                for record in result.get(category,[]) if record['kind']=='user_fact' and record['temporal']=='current']
        matched=set()
        case_tp=0
        for category,record in actual:
            retained+=1;traceable+=1
            found=next((i for i,expected in enumerate(case['expected']) if i not in matched
                and category==expected['category'] and normalized(record['key'])==normalized(expected['key'])
                and normalized(record['value']) in {normalized(v) for v in expected['values']}
                and ('scope_type' not in expected or record.get('scope_type')==expected['scope_type'])
                and ('scopes' not in expected or record.get('scope') in expected['scopes'])
                and ('valid_from' not in expected or record.get('valid_from')==expected['valid_from'])),None)
            if found is None:
                fp+=1
                if case.get('temporary'):temporary_fp+=1
            else:matched.add(found);tp+=1;case_tp+=1
        missing=len(case['expected'])-len(matched);fn+=missing
        rows.append({'id':case['id'],'matched':case_tp,'unexpected':len(actual)-case_tp,'missing':missing})
    return {'scope':'labeled_source_session_output_comparison','cases':rows,'true_positive':tp,
            'false_positive':fp,'false_negative':fn,'temporary_request_false_positive':temporary_fp,
            'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'structurally_traceable_retained':traceable,'retained':retained,
            'invalid_outputs':invalid,
            'semantic_measurement':'Explicit category/relation/value/scope labels; not a general entailment proof.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--allow-model-calls',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    data=json.loads((ROOT/'evals/source_session_holdout.json').read_text(encoding='utf-8'))
    if args.predictions and args.model_root:parser.error('Choose predictions or model-root, not both.')
    if args.model_root:
        if not args.allow_model_calls:parser.error('Model evaluation requires --allow-model-calls.')
        if len(data['cases'])>12:parser.error('This bounded run allows at most 12 fixture sessions.')
        from selfos.providers.knowledge import api_summarizer
        from selfos.providers import client
        from selfos.sources.text import redact
        opener_factory=client.request_opener;calls=0
        def counted_factory(root):
            opener=opener_factory(root)
            def request(*a,**kw):
                global calls
                if calls>=12:raise RuntimeError('Evaluation model-call limit reached')
                calls+=1
                return opener(*a,**kw)
            return request
        client.request_opener=counted_factory
        predictions={}
        try:
            generate=api_summarizer(args.model_root,review_records=False)
            for case in data['cases']:
                try:predictions[case['id']]=generate(prepare(case))
                except Exception as error:predictions[case['id']]={'_evaluation_error':redact(str(error))[:600]}
        finally:client.request_opener=opener_factory
        provenance='live_model'
    elif args.predictions:
        predictions=json.loads(args.predictions.read_text(encoding='utf-8'))
        provenance='supplied_predictions_unverified_origin';calls=0
    else:parser.error('Provide --predictions or explicitly authorized --model-root.')
    report={**score(data,predictions),'prediction_provenance':provenance,'model_calls':calls}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
