import selfos.providers.knowledge as _providers_knowledge
import urllib.request as _urllib_request
import selfos.web.server as _web_server
import selfos.app.pipeline as _app_pipeline
import selfos.knowledge.filtering as _knowledge_filtering
import selfos.knowledge.projects as _knowledge_projects
import selfos.storage.pipeline as _storage_pipeline
import selfos.sources.compaction as _sources_compaction
import copy
import json
import pytest


from tests.test_project_knowledge_contract import message, session, summary, card

@pytest.mark.parametrize('text',['Continue. Retry. Thanks.','继续。重试。谢谢。','ok; continue; retry','Thanks, continue.'])
def test_multiple_transient_sentences_are_filtered(text):
    assert _knowledge_filtering.compact_message(message(text)) is None

@pytest.mark.parametrize('text',['Continue. Next benchmark replay latency.',
    '继续。我们选择增量导入，因为需要保留来源。','Retry. Import failed with ValueError: unknown source.'])
def test_transient_prefix_does_not_erase_meaningful_context(text):
    assert _knowledge_filtering.compact_message(message(text)) is not None

def test_summarizer_does_not_call_model_for_transient_only_input(tmp_path,monkeypatch):

    monkeypatch.setattr(_providers_knowledge,'_get_api_config',lambda root:('test-key','http://unused'))
    monkeypatch.setattr(_urllib_request,'urlopen',lambda *args,**kwargs:pytest.fail('Noise must not reach model'))
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    result=_providers_knowledge.api_summarizer(tmp_path)(session('Continue. Retry. Thanks.'))
    assert result=={'project':None,'lessons':[],'personal_facts':[],'preferences':[],'history':[]}

@pytest.mark.parametrize("text", [
    "<local-command-stdout>Set model to Opus (1M context)</local-command-stdout>",
    "[external_agent_tool_result]Directory listing: tmp.py[/external_agent_tool_result]",
    "This session is being continued from a previous conversation that ran out of context. Summary: old task",
    "本次未完成有效审查：当前子代理没有可调用的文件读取或命令执行工具，无法检查源码及验证行号。",
    "# Update Config Skill\nModify Claude Code configuration by updating settings.json files.",
])
def test_runtime_noise_does_not_become_project_knowledge(text):
    assert _knowledge_filtering.compact_message(message(text)) is None

def test_quoted_ai_dialogue_is_not_user_authored_fact():
    m = message("以下是之前 AI 的回答：\n建议每次训练保留两次余力。把这部分抽取重要信息，放进来。")
    item = session()
    item["messages"] = [_knowledge_filtering.compact_message(m)]
    result = summary(item)
    result["lessons"] = [{"text": "Use two reps in reserve", "source_ids": ["m1"], "kind": "user_fact"}]
    assert _knowledge_projects.validate_summary(result, item)["lessons"][0]["kind"] == "assistant_suggestion"

def test_dated_failure_evidence_is_not_deleted_with_logs():
    m = _knowledge_filtering.compact_message(message("Fix import.\n2026-11-10T08:00:00Z ERROR ValueError: unknown source\nNext: repair mapping."))
    assert "ValueError: unknown source" in m["text"]
    assert "repair mapping" in m["text"]

def test_current_card_is_bounded_but_history_remains_available():
    c = None
    for i in range(30):
        c = _knowledge_projects.merge_project_card(c, card(decisions=[f"Decision {i}"], updated_at=f"2026-11-{i+1:02d}T08:00:00Z"))
    assert len(c["decisions"]) <= 8
    assert len(c["decision_history"]) == 30


@pytest.mark.parametrize('text',[
    'SelfOS Knowledge: scanning local Claude Code and Codex conversations\nScanned 21847 messages; compacted into 380 session parts\nKnowledge: 380 compact session parts, 380 pending; workers 3\nOrganizing session 1/380 ...\nSaved session 1/380; backup 20261110T171407-abcdef',
    'Knowledge: 21539 messages, 1509 new batches\nOrganizing batch 1/1509 ...\nSaved batch 1/1509: 6 facts; backup example',
    'ping','现在进行到哪里了？','怎么样了，可以继续吗？',
])
def test_import_progress_and_status_chatter_are_filtered(text):
    assert _knowledge_filtering.compact_message(message(text)) is None


def test_import_failure_is_evidence_and_not_personal_fact():
    item=_knowledge_filtering.compact_message(message('Organizing session 1/380 ...\nSession 1, attempt 2/2: Record quotation is not present in its sources\nKnowledge import failed: Invalid or untraceable knowledge fact'))
    assert item['provenance']=='runtime_evidence'
    assert 'Record quotation' in item['text']


def test_progress_paste_keeps_user_reasoning():
    item=_knowledge_filtering.compact_message(message('Organizing batch 1/1509 ...\nSaved batch 1/1509: 6 facts; backup example\n我们应该按会话归并，而不是固定消息数分批，因为这样能保留讨论上下文。'))
    assert '按会话归并' in item['text']
    assert 'Organizing batch' not in item['text']
    assert 'backup example' not in item['text']

def test_stable_title_does_not_follow_last_small_task():
    a = card(title="Alpha knowledge importer")
    b = card(title="Fix test_source_id", updated_at="2026-11-10T09:00:00Z")
    assert _knowledge_projects.merge_project_card(a, b)["title"] == "Alpha knowledge importer"


def test_decision_lineage_preserves_original_time_and_sources():
    first=card(decisions=['Use batches'],source_ids=['old'],updated_at='2026-11-01T08:00:00Z')
    later=card(decisions=['Use sessions'],source_ids=['new'],updated_at='2026-11-10T08:00:00Z')
    merged=_knowledge_projects.merge_project_card(first,later,limit=1)
    record=next(r for r in merged['decision_records'] if r['text']=='Use batches')
    assert record['source_ids']==['old']
    assert record['observed_at']=='2026-11-01T08:00:00Z'

def test_structured_chat_context_keeps_next_steps_and_omits_source_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(_web_server, "VAULT", tmp_path)
    c = card(decisions=["Historical implementation detail " * 200] * 100,
             next_steps=["Benchmark the repaired importer"], source_ids=["abcdef" * 100])
    (tmp_path / ".knowledge_pipeline.json").write_text(json.dumps({"cards": {c["project_id"]: c}, "lessons": []}))
    text = _web_server._load_vault_context()
    assert "Benchmark the repaired importer" in text
    assert "abcdef" * 100 not in text

def test_same_git_repository_exports_have_one_project_identity(tmp_path):
    repo = tmp_path / "alpha"
    repo.mkdir()
    (repo / ".git").mkdir()
    nested = repo / "src"
    nested.mkdir()
    a = message("Build Alpha", project=str(repo))
    b = message("Fix Alpha tests", identity="m2", project=str(nested), session="s2")
    assert len({s["project_id"] for s in _sources_compaction.prepare_sessions([a,b])}) == 1

def test_empty_summary_is_cached_without_fake_project(tmp_path):
    item = session()
    result = _app_pipeline.consolidate_sessions(tmp_path, [item], lambda _: {"project": None, "lessons": []})
    assert result["completed_sessions"] == 1
    assert not list((tmp_path / "02_Work/projects").glob("*.md"))
    assert _app_pipeline.consolidate_sessions(tmp_path, [item], lambda _: pytest.fail("replayed"))["model_calls"] == 0

def test_semantic_refinement_merges_lessons_without_changing_current_blocker(tmp_path):
    def with_lesson(item):
        result = summary(item, status="blocked", blockers=["Quota"])
        result["lessons"] = [{"text": "Use retries for temporary errors", "source_ids": ["m1"], "kind": "user_fact"},
                             {"text": "Retry transient failures", "source_ids": ["m1"], "kind": "user_fact"}]
        return result
    _app_pipeline.consolidate_sessions(tmp_path, [session()], with_lesson)
    def refine(payload):
        result = {"project": copy.deepcopy(payload["project"]), "lessons": [payload["lessons"][0]]}
        result["project"]["status"] = "completed"
        result["project"]["blockers"] = []
        return result
    _app_pipeline.refine_projects(tmp_path, refine)
    state = json.loads((tmp_path / ".knowledge_pipeline.json").read_text())
    assert len(state["lessons"]) == 1
    assert len(state["lesson_history"]) == 2
    assert next(iter(state["cards"].values()))["blockers"] == ["Quota"]

def test_refinement_rejects_fabricated_sources_and_keeps_original(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    original = (tmp_path / ".knowledge_pipeline.json").read_bytes()
    def invalid(payload):
        return {"project": {**payload["project"], "source_ids": ["invented"]}, "lessons": []}
    with pytest.raises(ValueError):
        _app_pipeline.refine_projects(tmp_path, invalid)
    assert (tmp_path / ".knowledge_pipeline.json").read_bytes() == original

def test_unchanged_project_synthesis_is_cached(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    _app_pipeline.refine_projects(tmp_path, lambda payload: {"project": payload["project"], "lessons": []})
    result = _app_pipeline.refine_projects(tmp_path, lambda _: pytest.fail("unchanged synthesis called"))
    assert result["projects"] == 0


def test_synthesis_algorithm_change_refreshes_only_final_merge(tmp_path,monkeypatch):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    monkeypatch.setattr(_app_pipeline,'SYNTHESIS_VERSION',1,raising=False)
    refine=lambda payload:{'project':payload['project'],'lessons':[]}
    _app_pipeline.refine_projects(tmp_path,refine)
    monkeypatch.setattr(_app_pipeline,'SYNTHESIS_VERSION',2)
    assert _app_pipeline.refine_projects(tmp_path,refine)['projects']==1
    assert _app_pipeline.consolidate_sessions(tmp_path,[session()],lambda _:pytest.fail('Session extraction replayed'))['model_calls']==0


def test_synthesis_counts_routing_calls_and_retries(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    attempts=[]
    def refine(payload):
        attempts.append(True)
        if len(attempts)==1:
            error=TimeoutError('Routing failed');error.additional_api_calls=2;raise error
        return {'project':payload['project'],'lessons':[],'_additional_api_calls':1}
    assert _app_pipeline.refine_projects(tmp_path,refine)['model_calls']==5


def test_cancelled_routing_does_not_retry_or_write_partial_synthesis(tmp_path):
    from concurrent.futures import CancelledError
    _app_pipeline.consolidate_sessions(tmp_path,[session()],summary)
    path=tmp_path/'.knowledge_pipeline.json';previous=path.read_bytes();stopped=[];logs=[];calls=[]
    def refine(payload):
        calls.append(True);stopped.append(True)
        error=CancelledError('Stopped in review');error.additional_api_calls=1;raise error
    result=_app_pipeline.refine_projects(tmp_path,refine,cancel=lambda:bool(stopped),progress=logs.append)
    assert len(calls)==1 and result['model_calls']==2 and result['projects']==0
    assert path.read_bytes()==previous
    assert not any('retry' in line.lower() for line in logs)

def test_refinement_retries_temporary_failure(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    attempts = []
    def flaky(payload):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("temporary")
        return {"project": payload["project"], "lessons": []}
    assert _app_pipeline.refine_projects(tmp_path, flaky)["projects"] == 1


def test_project_synthesis_has_no_arbitrary_twelve_lesson_quota(tmp_path):
    def extract(item):
        result=summary(item);identity=item['messages'][0]['id']
        indices=range(8) if identity=='m1' else range(8,15)
        result['lessons']=[{'text':f'Independent method {i}','kind':'inference',
            'domain':'work','source_ids':[identity]} for i in indices]
        return result
    _app_pipeline.consolidate_sessions(tmp_path,[session(),session(identity='m2',session='s2')],extract)
    def refine(payload):
        return {'project':payload['project'],'lessons':payload['lessons']}
    _app_pipeline.refine_projects(tmp_path,refine)
    state=json.loads((tmp_path/'.knowledge_pipeline.json').read_text())
    assert len(state['lessons'])==15

def test_lesson_only_summary_still_validates_sources(tmp_path):
    def lesson_only(_):
        return {"project": None, "lessons": [{"text":"Use bounded retries", "source_ids":["m1"], "kind":"inference"}]}
    result = _app_pipeline.consolidate_sessions(tmp_path, [session()], lesson_only)
    assert result["completed_sessions"] == 1
    assert "Use bounded retries" in (tmp_path / "05_Life/lessons.md").read_text()

def test_rebuild_replacement_removes_old_card_and_can_restore(tmp_path):
    scratch = tmp_path / "scratch"
    vault = tmp_path / "vault"
    _app_pipeline.consolidate_sessions(vault, [session()], summary)
    _app_pipeline.consolidate_sessions(scratch, [session(project="C:/projects/beta", identity="m2", session="s2")], summary)
    _app_pipeline.refine_projects(scratch, lambda payload: {"project":payload["project"],"lessons":[]})
    original = (vault / ".knowledge_pipeline.json").read_bytes()
    run = _app_pipeline.install_rebuilt(vault, scratch)
    assert len(list((vault / "02_Work/projects").glob("*.md"))) == 1
    assert "beta" in next((vault / "02_Work/projects").glob("*.md")).read_text()
    _storage_pipeline.restore_pipeline_backup(vault, run)
    assert (vault / ".knowledge_pipeline.json").read_bytes() == original

def test_chinese_checkpoint_resumes_on_windows(tmp_path):
    def chinese(item):
        result = summary(item)
        result["project"].update(title="个人知识库", intent="整理代码讨论和项目目标")
        return result
    _app_pipeline.consolidate_sessions(tmp_path, [session()], chinese)
    assert _app_pipeline.consolidate_sessions(tmp_path, [session()], lambda _: pytest.fail("cached"))["model_calls"] == 0

def test_wrapped_tool_failure_is_kept_as_evidence_without_becoming_user_fact():
    raw = message("[external_agent_tool_result]FAILED test_source_mapping - ValueError: unknown source[/external_agent_tool_result]")
    compacted = _knowledge_filtering.compact_message(raw)
    assert compacted is not None
    assert "FAILED test_source_mapping" in compacted["text"]
    item = {**session(), "messages":[compacted]}
    candidate = summary(item)
    candidate["lessons"] = [{"text":"Fix source mapping", "source_ids":["m1"], "kind":"user_fact"}]
    assert _knowledge_projects.validate_summary(candidate,item)["lessons"][0]["kind"] != "user_fact"

def test_explicit_project_aliases_merge_cards_and_preserve_original_paths(tmp_path):
    items = [session(), session(project="C:/copies/alpha", identity="m2", session="s2")]
    _app_pipeline.consolidate_sessions(tmp_path, items, summary)
    _app_pipeline.register_project_aliases(tmp_path, {"C:/copies/alpha":"C:/projects/alpha"})
    state = json.loads((tmp_path / ".knowledge_pipeline.json").read_text(encoding="utf-8"))
    assert len(state["cards"]) == 1
    assert state["sources"]["m2"]["original_project_id"] == "C:/copies/alpha"
    prepared = _sources_compaction.prepare_sessions([message("Fix Alpha", project="C:/copies/alpha")], aliases=state["project_aliases"])
    assert prepared[0]["project_id"] == "C:/projects/alpha"

def test_semantic_rephrasing_does_not_invalidate_synthesis_cache(tmp_path):
    def initial(item):
        candidate=summary(item)
        candidate["lessons"]=[{"text":"Retry transient failures", "source_ids":["m1"], "kind":"inference"}]
        return candidate
    _app_pipeline.consolidate_sessions(tmp_path,[session()],initial)
    def refine(payload):
        return {"project":payload["project"],"lessons":[{"text":"Use bounded retries for temporary API errors", "source_ids":["m1"], "kind":"inference"}]}
    _app_pipeline.refine_projects(tmp_path,refine)
    assert _app_pipeline.refine_projects(tmp_path,lambda _:pytest.fail("rephrasing replayed"))["projects"] == 0

def test_refinement_metadata_cannot_promote_user_wrapped_tool_evidence():
    item=session()
    item["messages"][0].update(text="",provenance="runtime_evidence")
    candidate=summary(item)
    candidate["lessons"]=[{"text":"Use retries", "source_ids":["m1"], "kind":"user_fact"}]
    assert _knowledge_projects.validate_summary(candidate,item)["lessons"][0]["kind"] != "user_fact"

def test_rebuild_preserves_unmanaged_manual_lessons(tmp_path):
    vault,scratch=tmp_path/"vault",tmp_path/"scratch"
    _app_pipeline.consolidate_sessions(vault,[session()],summary)
    (vault/"05_Life").mkdir()
    (vault/"05_Life/lessons.md").write_text("# My notes\nManual learning note: check assumptions.\n",encoding="utf-8")
    _app_pipeline.consolidate_sessions(scratch,[session()],summary)
    _app_pipeline.refine_projects(scratch,lambda payload:{"project":payload["project"],"lessons":[]})
    _app_pipeline.install_rebuilt(vault,scratch)
    assert "Manual learning note: check assumptions." in (vault/"05_Life/lessons.md").read_text(encoding="utf-8")

def test_chat_keeps_long_next_step_outcome(tmp_path,monkeypatch):
    monkeypatch.setattr(_web_server,"VAULT",tmp_path)
    c=card(next_steps=["Review the imported sources. " * 20+"Then benchmark source coverage."])
    (tmp_path/".knowledge_pipeline.json").write_text(json.dumps({"cards":{"alpha":c},"lessons":[]}))
    assert "Then benchmark source coverage." in _web_server._load_vault_context()

def test_agent_wakeup_command_is_not_a_project_next_step():
    item=session()
    candidate=summary(item,next_steps=["Call ScheduleWakeup(stop=true) upon completion","Implement a stop button for long imports"])
    assert _knowledge_projects.validate_summary(candidate,item)["project"]["next_steps"] == ["Implement a stop button for long imports"]


def test_automatic_goal_continuation_is_filtered_without_touching_original():
    text='<codex_internal_context source="goal">Continue the active goal. <objective>Improve the project.</objective></codex_internal_context>'
    value=message(text)
    original=copy.deepcopy(value)
    assert _knowledge_filtering.content_identity(value)=='machine_summary'
    assert _knowledge_filtering.compact_message(value) is None
    assert value==original


def test_human_debugging_request_about_internal_context_remains():
    text='We are debugging repeated goal notifications. Here is the example: <codex_internal_context source="goal">Continue</codex_internal_context>'
    result=_knowledge_filtering.compact_message(message(text))
    assert result is not None and 'debugging repeated goal notifications' in result['text']


def test_actual_question_reply_is_not_mistaken_for_automatic_goal_context():
    text='<send_user_message_question_reply>[{"question":"Write directly?","answer":"Write directly, retaining backups and sources."}]</send_user_message_question_reply>'
    result=_knowledge_filtering.compact_message(message(text))
    assert result is not None and 'retaining backups and sources' in result['text']
