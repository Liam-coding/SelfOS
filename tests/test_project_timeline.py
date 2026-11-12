import copy


def fixture():
    sources = {
        "a": {"project_id": "alpha", "timestamp": "2026-01-01T08:00:00Z", "role": "user"},
        "b": {"project_id": "alpha", "timestamp": "2026-01-02T08:00:00Z", "role": "assistant"},
        "c": {"project_id": "alpha", "timestamp": "2026-01-03T08:00:00Z", "role": "user"},
    }
    snapshots = []
    for identity, intent, status, blockers in [
        ("a", "Build a local importer", "blocked", ["Missing adapter"]),
        ("b", "Build an incremental importer", "in_progress", []),
        ("c", "Build an incremental importer", "completed", []),
    ]:
        snapshots.append(dict(project_id="alpha", title="Alpha", intent=intent,
            status=status, blockers=blockers, next_steps=[], decisions=["Use local storage"],
            updated_at=sources[identity]["timestamp"], source_ids=[identity], verified=False))
    current = {**snapshots[-1], "source_ids": ["a", "b", "c"]}
    return {"cards": {"alpha": current}, "sources": sources,
        "summaries": {identity: {"project": snapshot} for identity, snapshot in zip(sources, snapshots)}}


def project(state):
    from selfos.knowledge.timeline import project_timeline
    return project_timeline(state, "alpha")


def test_three_sessions_preserve_changing_goals_and_blockers_without_invented_dates():
    state = fixture()
    before = copy.deepcopy(state)
    result = project(state)
    assert state == before
    assert result["current"]["status"] == "completed"
    entries = result["entries"]
    goals = [entry for entry in entries if entry["type"] == "goals"]
    assert {entry["text"] for entry in goals} == {"Build a local importer", "Build an incremental importer"}
    assert any(entry["type"] == "blockers" and "Missing adapter" in entry["text"] for entry in entries)
    assert all(not entry["event_time"] and not entry["imported_at"] for entry in entries)
    assert all(entry["source_ids"] for entry in entries)
    assert all(not entry.get("superseded") for entry in goals)


def test_late_arriving_summaries_order_by_known_observation_not_insertion_order():
    state = fixture()
    expected = project(state)["entries"]
    state["summaries"] = dict(reversed(list(state["summaries"].items())))
    assert project(state)["entries"] == expected
    dates = [entry["observed_at"] for entry in expected if entry["observed_at"]]
    assert dates == sorted(dates)


def test_legacy_project_context_does_not_invent_event_or_observation_time():
    state = fixture()
    state["summaries"] = {}
    state["cards"]["alpha"]["decision_history"] = ["Use legacy adapter"]
    state["cards"]["alpha"]["state_records"] = [dict(
        status="blocked", blockers=["Old blocker"], next_steps=[], source_ids=["a"],
        source_scope="project_context", observed_at="2026-01-01T08:00:00Z", verified=False)]
    entries = project(state)["entries"]
    legacy = [entry for entry in entries if entry["source_scope"] == "project_context"]
    assert legacy
    assert all(not entry["event_time"] and not entry["observed_at"] for entry in legacy)
    assert any(entry["source_times"] for entry in legacy)


def test_current_state_comes_from_canonical_card_after_manual_change_or_restore():
    state = fixture()
    assert project(state)["current"]["status"] == "completed"
    state["cards"]["alpha"]["status"] = "paused"
    assert project(state)["current"]["status"] == "paused"
    state["cards"]["alpha"]["status"] = "blocked"
    assert project(state)["current"]["status"] == "blocked"


def test_equal_time_different_snapshots_remain_visible_with_separate_sources():
    state = fixture()
    state["sources"]["b"]["timestamp"] = state["sources"]["a"]["timestamp"]
    state["summaries"]["b"]["project"]["updated_at"] = state["sources"]["a"]["timestamp"]
    entries = project(state)["entries"]
    progress = [entry for entry in entries if entry["type"] == "progress"]
    assert any(entry["status"] == "blocked" and entry["source_ids"] == ["a"] for entry in progress)
    assert any(entry["status"] == "in_progress" and entry["source_ids"] == ["b"] for entry in progress)


def test_context_sources_do_not_promote_model_summary_to_verified_user_claim():
    entries = project(fixture())["entries"]
    contextual = [entry for entry in entries if "b" in entry["source_ids"]]
    assert contextual
    assert all(entry["kind"] == "inference" and not entry["verified"] for entry in contextual)


def test_malformed_optional_lineage_does_not_break_other_valid_observations():
    state = fixture()
    state["cards"]["alpha"]["state_inputs"] = None
    state["cards"]["alpha"]["decision_records"] = None
    state["summaries"]["broken"] = {"project": {"project_id": "alpha", "intent": "Old goal", "source_ids": None}}
    assert project(state)["entries"]


def test_aliases_resolve_without_including_another_projects_summary():
    state = fixture()
    state["project_aliases"] = {"old-alpha": "alpha"}
    state["summaries"]["a"]["project"]["project_id"] = "old-alpha"
    state["summaries"]["other"] = {"project": {"project_id": "beta", "intent": "PRIVATE OTHER PROJECT", "source_ids": ["a"]}}
    from selfos.knowledge.timeline import project_timeline
    assert project_timeline(state, "old-alpha") == project(state)
    assert "PRIVATE OTHER PROJECT" not in str(project(state))


def test_non_iso_and_ambiguous_dates_remain_unknown():
    state = fixture()
    for source in state["sources"].values():
        source["timestamp"] = "20260101"
    for summary in state["summaries"].values():
        summary["project"]["updated_at"] = "2026-01-01T08:00:00"
        summary["project"]["event_time"] = "20260101"
    assert all(not entry["event_time"] and not entry["observed_at"] and not entry["source_times"]
               for entry in project(state)["entries"])


def test_string_source_ids_are_not_split_into_character_references():
    state = fixture()
    state["summaries"]["a"]["project"]["source_ids"] = "abc"
    goals = [entry for entry in project(state)["entries"] if entry["text"] == "Build a local importer"]
    assert goals[0]["source_ids"] == []


def test_same_session_state_lineage_does_not_duplicate_summary_milestone():
    state = fixture()
    snapshot = state["summaries"]["a"]["project"]
    state["cards"]["alpha"]["state_inputs"] = [{
        **snapshot, "observed_at": snapshot["updated_at"], "source_scope": "session_context"}]
    result = project(state)
    assert len([entry for entry in result["entries"] if entry["type"] == "progress" and entry["source_ids"] == ["a"]]) == 1


def test_explicit_event_and_import_times_remain_distinct_from_observation():
    state = fixture()
    state["summaries"]["a"]["project"].update(event_time="2025-12-31", imported_at="2026-02-01T00:00:00Z")
    entry = next(entry for entry in project(state)["entries"] if entry["source_ids"] == ["a"])
    assert entry["event_time"] == "2025-12-31"
    assert entry["observed_at"] == "2026-01-01T08:00:00Z"
    assert entry["imported_at"] == "2026-02-01T00:00:00Z"
    assert entry["ordering_basis"] == "event"


def test_partial_summaries_preserve_uncovered_legacy_decision_without_date():
    state = fixture()
    state['cards']['alpha']['decision_history'] = ['Old adapter decision', 'Use local storage']
    entries = project(state)['entries']
    old = [entry for entry in entries if entry['text'] == 'Old adapter decision']
    assert len(old) == 1 and not old[0]['observed_at']
    assert old[0]['source_scope'] == 'project_context'
    assert len([entry for entry in entries if entry['text'] == 'Use local storage']) == 3


def test_real_merged_decision_lineage_adds_no_duplicate_covered_observations():
    from selfos.knowledge.projects import merge_project_card
    state = fixture()
    merged = None
    for summary in state['summaries'].values():
        merged = merge_project_card(merged, summary['project'])
    state['cards']['alpha'] = merged
    decisions = [entry for entry in project(state)['entries'] if entry['type'] == 'decisions']
    assert len(decisions) == 3
    assert {tuple(entry['source_ids']) for entry in decisions} == {('a',), ('b',), ('c',)}


def test_invalid_optional_decision_text_does_not_break_valid_timeline():
    expected = project(fixture())
    for text in [None, {}, [], '', '   ']:
        state = fixture()
        state['cards']['alpha']['decision_records'] = [{'text': text, 'source_ids': []}]
        assert project(state) == expected
