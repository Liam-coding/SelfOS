"""Source selection must fail closed before reading conversation content."""
import json
import os
from pathlib import Path

import pytest


def test_source_registry_preserves_missing_roots_and_prefix_exclusions(tmp_path):
    from selfos.sources.selection import load_sources, save_sources, allowed_source
    root = tmp_path / "conversations"
    root.mkdir()
    private = root / "private"
    selection = save_sources(tmp_path / "vault", {
        "roots": [str(root)], "exclusions": [str(private)]})
    assert allowed_source(root / "public.jsonl", selection)
    assert not allowed_source(private / "session.jsonl", selection)
    assert allowed_source(root / "private-other.jsonl", selection)
    root.rmdir()
    assert load_sources(tmp_path / "vault")["roots"] == [str(root.resolve())]


@pytest.mark.parametrize("value", [
    {"roots": ["relative"], "exclusions": []},
    {"roots": [], "exclusions": ["relative"]},
    {"roots": "wrong", "exclusions": []},
])
def test_invalid_source_settings_do_not_create_registry(tmp_path, value):
    from selfos.sources.selection import save_sources
    with pytest.raises(ValueError):
        save_sources(tmp_path, value)
    assert not (tmp_path / ".knowledge_sources.json").exists()


def test_exclusion_cannot_authorize_or_reference_outside_root(tmp_path):
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(ValueError):
        save_sources(tmp_path / "vault", {
            "roots": [str(root)], "exclusions": [str(tmp_path / "outside")]})


def test_discovery_is_metadata_only_and_defaults_do_not_write(tmp_path):
    from selfos.sources.selection import discover_sources, load_sources
    root = tmp_path / "source"
    root.mkdir()
    missing = tmp_path / "missing"
    rows = discover_sources(defaults=[root, missing])
    assert [row["available"] for row in rows] == [True, False]
    assert load_sources(tmp_path / "vault", defaults=[root])["roots"] == [str(root)]
    assert not (tmp_path / "vault").exists()


def _conversation(path, count=30):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "user", "sessionId": path.stem,
             "timestamp": f"2026-11-13T10:00:{index:02d}",
             "message": {"content": f"I prefer readable Python functions and explicit error handling for project {path.stem}, decision {index}."}}
            for index in range(count)]
    path.write_text(chr(10).join(json.dumps(row) for row in rows), encoding="utf-8")
    return path.read_bytes()


def test_preview_is_bounded_preserves_sources_and_rejects_changed_content(tmp_path):
    from selfos.app.onboarding import build_preview, resolve_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    originals = {}
    for index in range(4):
        path = root / f"session-{index}.jsonl"
        originals[path] = _conversation(path)
        os.utime(path, (100 + index, 100 + index))
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    assert len(preview["files"]) == 2
    assert {Path(item["path"]).name for item in preview["files"]} == {"session-2.jsonl", "session-3.jsonl"}
    assert len(preview["sessions"]) <= 2
    assert all(len(item["messages"]) <= 20 for item in preview["sessions"])
    assert preview["clipped"]
    assert preview["budget_limit"] == 12
    assert resolve_preview(vault, preview["id"])["sessions"] == preview["sessions"]
    assert all(path.read_bytes() == original for path, original in originals.items())
    changed = Path(preview["files"][0]["path"])
    changed.write_bytes(changed.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        resolve_preview(vault, preview["id"])


def test_oversize_sources_are_skipped_before_content_read(tmp_path):
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    _conversation(root / "small.jsonl", 2)
    large = root / "large.jsonl"
    with large.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024 + 1)
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    assert [Path(item["path"]).name for item in preview["files"]] == ["small.jsonl"]
    assert any(item["code"] == "oversize" for item in preview["warnings"])


def test_source_setting_change_requires_fresh_preview(tmp_path):
    from selfos.app.onboarding import build_preview, resolve_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    _conversation(root / "session.jsonl", 2)
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    save_sources(vault, {"roots": [str(root)], "exclusions": [str(root / "session.jsonl")]})
    with pytest.raises(ValueError, match="changed"):
        resolve_preview(vault, preview["id"])


def test_modified_preview_cannot_inject_model_context(tmp_path):
    from selfos.app.onboarding import build_preview, resolve_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    _conversation(root / "session.jsonl", 2)
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    path = vault / ".knowledge_onboarding" / "previews" / (preview["id"] + ".json")
    preview["sessions"][0]["messages"][0]["text"] = "Injected unrelated personal information"
    path.write_text(json.dumps(preview), encoding="utf-8")
    with pytest.raises(ValueError, match="changed|Invalid"):
        resolve_preview(vault, preview["id"])


def test_enumeration_limit_applies_to_non_jsonl_entries(tmp_path):
    from selfos.sources.selection import select_files
    root = tmp_path / "source"
    root.mkdir()
    for index in range(12):
        (root / f"entry-{index}.txt").touch()
    files, warnings = select_files({"roots": [str(root)], "exclusions": []}, entry_limit=5)
    assert files == []
    assert any(item["code"] == "enumeration_limit" for item in warnings)


def test_more_is_explicit_bounded_new_allowance(tmp_path):
    from selfos.app.onboarding import build_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    for index in range(5):
        _conversation(root / f"session-{index}.jsonl", 45)
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault, tier="more")
    assert len(preview["files"]) == 4
    assert len(preview["sessions"]) == 4
    assert all(len(session["messages"]) <= 40 for session in preview["sessions"])
    assert preview["budget_limit"] == 24
    with pytest.raises(ValueError):
        build_preview(vault, tier="all")


def test_policy_change_invalidates_preview(tmp_path):
    from selfos.app.onboarding import build_preview, resolve_preview
    from selfos.sources.selection import save_sources
    root = tmp_path / "source"
    _conversation(root / "session.jsonl", 2)
    vault = tmp_path / "vault"
    save_sources(vault, {"roots": [str(root)], "exclusions": []})
    preview = build_preview(vault)
    from selfos.storage.settings import save_settings
    save_settings(vault, {"domains": ["work"], "detail": "concise"})
    with pytest.raises(ValueError, match="changed"):
        resolve_preview(vault, preview["id"])


def test_source_link_cannot_escape_selected_root(tmp_path):
    from selfos.sources.selection import select_files
    root = tmp_path / "source"
    root.mkdir()
    outside = tmp_path / "outside.jsonl"
    _conversation(outside, 2)
    try:
        (root / "linked.jsonl").symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit unprivileged symbolic links")
    files, warnings = select_files({"roots": [str(root)], "exclusions": []})
    assert files == []
    assert any(item["code"] == "symlink" for item in warnings)
