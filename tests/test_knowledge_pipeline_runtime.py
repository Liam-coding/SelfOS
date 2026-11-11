import selfos.providers.knowledge as _providers_knowledge
import urllib.request as _urllib_request
import selfos.storage.files as _storage_files
import selfos.storage.pipeline as _storage_pipeline
import selfos.sources.conversations as _sources_conversations
import selfos.app.pipeline as _app_pipeline
import selfos.knowledge.projects as _knowledge_projects
import selfos.knowledge.filtering as _knowledge_filtering
import selfos.sources.compaction as _sources_compaction
import json
import threading
import pytest

from tests.test_project_knowledge_contract import session, summary, card



def test_stop_does_not_schedule_next_session_and_resume_keeps_completed(tmp_path):
    stop = threading.Event()
    items = [session(identity=f"m{i}", session=f"s{i}") for i in range(4)]
    def summarize(item):
        stop.set()
        return summary(item)
    result = _app_pipeline.consolidate_sessions(tmp_path, items, summarize, max_workers=1, cancel=stop.is_set)
    assert result["cancelled"]
    assert result["model_calls"] == 1
    assert result["completed_sessions"] == 1
    result = _app_pipeline.consolidate_sessions(tmp_path, items, summary)
    assert result["model_calls"] == 3


def test_backup_restores_project_and_cache(tmp_path):
    result = _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    _storage_pipeline.restore_pipeline_backup(tmp_path, result["run_id"])
    assert not list((tmp_path / "02_Work/projects").glob("*.md"))
    assert _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)["model_calls"] == 1


def test_pre_cancelled_does_not_call_model(tmp_path):
    result = _app_pipeline.consolidate_sessions(tmp_path, [session()], lambda _: pytest.fail("called"), cancel=lambda: True)
    assert result["model_calls"] == 0


def test_cache_preserves_source_metadata(tmp_path):
    _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    data = json.loads((tmp_path / ".knowledge_pipeline.json").read_text())
    assert data["sources"]["m1"]["path"] == "s1.jsonl"


def test_symlink_target_cannot_escape_vault(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (tmp_path / "02_Work").mkdir()
    try:
        (tmp_path / "02_Work/projects").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError):
        _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    assert list(outside.iterdir()) == []


def test_extractor_preserves_canonical_project_and_original_session(tmp_path):
    rows = [{"type": "session_meta", "payload": {"id": "original-session", "cwd": "C:/client-a/app"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "Build reliable project import."}]}}]
    (tmp_path / "export.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    result = _sources_conversations.extract_conversations([tmp_path])[0]
    assert result["session_id"] == "original-session"
    assert result["project_id"] == "C:/client-a/app"


def test_summary_api_maps_aliases_and_does_not_send_local_paths(monkeypatch):
    captured = []
    item = session()
    response = summary(item)
    response["project"]["project_id"] = "current-project"
    response["project"]["source_ids"] = ["s1"]
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps({"content": [{"type": "text", "text": json.dumps(response)}]}).encode()
    def request(req, **kwargs):
        captured.append(json.loads(req.data))
        return Response()
    monkeypatch.setattr(_providers_knowledge, "_get_api_config", lambda _: ("test-key", "https://example.test"))
    monkeypatch.setattr(_urllib_request, "urlopen", request)
    monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: _urllib_request.urlopen)
    result = _providers_knowledge.api_summarizer(None)(item)
    assert result["project"]["source_ids"] == ["m1"]
    assert result["project"]["project_id"] == "C:/projects/alpha"
    assert "C:/projects/alpha" not in json.dumps(captured)
    assert "s1.jsonl" not in json.dumps(captured)


def test_partial_write_is_recovered_and_retry_does_not_skip_session(tmp_path, monkeypatch):
    real = _storage_files._atomic_write
    def fail(path, data):
        if path.name == ".knowledge_pipeline.json":
            raise OSError("disk failure")
        real(path, data)
    with monkeypatch.context() as scoped:
        scoped.setattr(_storage_files, "_atomic_write", fail)
        with pytest.raises(OSError):
            _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)
    assert not list((tmp_path / "02_Work/projects").glob("*.md"))
    assert _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)["model_calls"] == 1


def test_out_of_order_concurrent_commits_restore_in_actual_order(tmp_path):
    import time
    items = [session(identity="m1", session="slow"), session(identity="m2", session="fast")]
    def summarize(item):
        if item["session_id"] == "slow":
            time.sleep(0.05)
        return summary(item)
    result = _app_pipeline.consolidate_sessions(tmp_path, items, summarize, max_workers=2)
    _storage_pipeline.restore_pipeline_backup(tmp_path, result["run_id"])
    assert not list((tmp_path / "02_Work/projects").glob("*.md"))


def test_unknown_status_does_not_resolve_existing_blocker():
    result = _knowledge_projects.merge_project_card(card(status="blocked", blockers=["Quota"]),
        card(status="unknown", blockers=[], next_steps=[], updated_at="2026-11-10T10:00:00Z"))
    assert result["status"] == "blocked"
    assert result["blockers"] == ["Quota"]


def test_equal_timestamp_parts_use_original_order_instead_of_completion_order():
    first = _knowledge_projects.validate_summary(summary(session(), status="blocked"), {**session(), "part": 0})
    last = _knowledge_projects.validate_summary(summary(session(), status="paused"), {**session(), "part": 1})
    assert _knowledge_projects.merge_project_card(last["project"], first["project"])["status"] == "paused"


def test_bulk_unfenced_json_keeps_purpose_and_tail():
    text = "Import mapping test result:\n" + json.dumps([{"targetArtifactType": "MIG", "rows": list(range(20000))}]) + "\nNext: repair empty references."
    result = _knowledge_filtering.compact_message({**session()["messages"][0], "text": text})
    assert len(result["text"]) < len(text) * 0.1
    assert "Import mapping test result" in result["text"]
    assert "repair empty references" in result["text"]


def test_scanning_and_preparation_can_be_cancelled(tmp_path):
    assert _sources_conversations.extract_conversations([tmp_path], cancel=lambda: True) == []
    assert _sources_compaction.prepare_sessions([session()["messages"][0]], cancel=lambda: True) == []


def test_dead_import_lock_is_reclaimed_before_journal_recovery(tmp_path):
    import subprocess, sys
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    (tmp_path / ".knowledge.lock").write_text(str(proc.pid))
    assert _app_pipeline.consolidate_sessions(tmp_path, [session()], summary)["completed_sessions"] == 1


def test_model_project_prose_is_redacted_before_storage(tmp_path):
    def summarize(item):
        result = summary(item)
        result["project"]["intent"] = "Contact person@example.com about import"
        result["project"]["decisions"] = ["Notify person@example.com"]
        return result
    _app_pipeline.consolidate_sessions(tmp_path, [session()], summarize)
    text = next((tmp_path / "02_Work/projects").glob("*.md")).read_text()
    assert "person@example.com" not in text


def test_unknown_summary_does_not_promote_inherited_status_timestamp():
    a = card(status="blocked", updated_at="2026-11-10T08:00:00Z")
    b = card(status="in_progress", blockers=[], updated_at="2026-11-10T09:00:00Z")
    c = card(status="unknown", blockers=[], updated_at="2026-11-10T10:00:00Z")
    assert _knowledge_projects.merge_project_card(_knowledge_projects.merge_project_card(a, c), b)["status"] == "in_progress"
    assert _knowledge_projects.merge_project_card(_knowledge_projects.merge_project_card(a, b), c)["status"] == "in_progress"
