"""The frozen live evaluator must reach the actual prepared-session summarizer."""
import selfos.providers.knowledge as _providers_knowledge
import selfos.app.pipeline_api as _app_pipeline_api




def test_pipeline_exposes_actual_summarizer_factory_without_transforming_output(monkeypatch):
    calls=[];output={'project':None,'lessons':[],'personal_facts':[],'_additional_api_calls':1}
    def factory(root,**kwargs):
        calls.append((root,kwargs))
        def generate(session):calls.append(session);return output
        return generate
    monkeypatch.setattr(_providers_knowledge,'api_summarizer',factory)
    generate=_app_pipeline_api.api_summarizer('test-root',review_records=False)
    session={'project_id':'synthetic/actual-contract','messages':[]}
    assert generate(session) is output
    assert calls==[('test-root',{'review_records':False}),session]
