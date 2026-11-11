import json
import knowledge_pipeline as pipeline
from knowledge_lesson_review import review_reusable_records
from tests.test_project_knowledge_contract import session,summary


def test_work_only_refinement_keeps_legacy_observation_in_work(tmp_path):
    def extract(item):
        result=summary(item)
        result['lessons']=[{'text':'This project used the 0.15 threshold.','source_ids':['m1'],'kind':'inference','domain':'work'}]
        return result
    pipeline.consolidate_sessions(tmp_path,[session()],extract,settings={'domains':['work'],'detail':'balanced'})
    path=tmp_path/'.knowledge_pipeline.json';state=json.loads(path.read_text())
    state['lessons'][0].pop('domain')
    path.write_text(json.dumps(state),encoding='utf-8')
    def request(req,**kwargs):
        body=json.loads(req.data);prompt=json.loads(body['messages'][0]['content'])
        verdicts=[{'id':row['id'],'action':'observation','lesson_group':'','lesson_text':'',
                   'observation_text':row['text'],'reason':'Local project setting.'} for row in prompt['candidates']]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return json.dumps({'content':[{'type':'tool_use','name':'route_knowledge','input':{'verdicts':verdicts}}]}).encode()
        return Response()
    def refine(payload):
        return review_reusable_records({'project':payload['project'],'lessons':payload['lessons'],'observations':[]},
                                       'test','https://example.test',open_request=request)
    pipeline.refine_projects(tmp_path,refine)
    current=json.loads(path.read_text())
    assert current['project_observations'][0]['domain']=='work'
    assert current['project_observations'][0]['text']=='This project used the 0.15 threshold.'
    assert current['project_observations'][0]['source_ids']==['m1']
    assert not current['lessons']
