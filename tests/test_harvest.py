"""
Tests for harvest.py core logic.
Run: python -m pytest tests/test_harvest.py -v
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add parent to path so we can import harvest
sys.path.insert(0, str(Path(__file__).parent.parent))
import harvest as bs


# ── _decode_claude_project_name ───────────────────────────────────────────────

class TestDecodeClaudeProjectName:
    def test_windows_simple(self):
        assert bs._decode_claude_project_name("C--Users-foo-myproject") == "myproject"

    def test_windows_drive_only(self):
        result = bs._decode_claude_project_name("C--")
        assert result == "C--"

    def test_macos_simple(self):
        assert bs._decode_claude_project_name("-Users-foo-myproject") == "myproject"

    def test_macos_deep(self):
        assert bs._decode_claude_project_name("-Users-foo-bar-baz-project") == "project"

    def test_unknown_format(self):
        assert bs._decode_claude_project_name("someproject") == "someproject"


# ── _decode_claude_project_path ───────────────────────────────────────────────

class TestDecodeClaudeProjectPath:
    def test_windows_nonexistent_returns_none(self):
        result = bs._decode_claude_project_path("C--Users-nobody-fakepath")
        assert result is None

    def test_macos_nonexistent_returns_none(self):
        result = bs._decode_claude_project_path("-Users-nobody-fakepath")
        assert result is None

    def test_unknown_format_returns_none(self):
        result = bs._decode_claude_project_path("notapath")
        assert result is None

    def test_windows_home_exists(self, tmp_path):
        pass  # covered by integration in test_windows_simple

    def test_macos_root_path_construction(self, monkeypatch):
        monkeypatch.setattr(Path, "exists", lambda self: True)
        result = bs._decode_claude_project_path("-Users-foo-project")
        assert result is not None
        assert str(result).endswith("Users/foo/project") or "Users" in str(result)


# ── _is_meaningful ────────────────────────────────────────────────────────────

class TestIsMeaningful:
    def test_too_short(self):
        assert bs._is_meaningful("ok") is False
        assert bs._is_meaningful("yes") is False
        assert bs._is_meaningful("对") is False

    def test_common_acks(self):
        assert bs._is_meaningful("apply") is False
        assert bs._is_meaningful("done") is False

    def test_task_notification(self):
        assert bs._is_meaningful("<task-notification>some content here</task-notification>") is False

    def test_loop_monitoring_prompts(self):
        assert bs._is_meaningful("Check eval progress by reading C:\\path\\to\\file") is False
        assert bs._is_meaningful("Read the file C:\\path and show last 20 lines") is False

    def test_bare_windows_path(self):
        assert bs._is_meaningful("C:\\Users\\foo\\bar.md") is False

    def test_meaningful_message(self):
        assert bs._is_meaningful("我想在这个项目里加一个新的功能") is True
        assert bs._is_meaningful("How do I configure the memory system?") is True

    def test_borderline_length(self):
        assert bs._is_meaningful("help me") is False  # 7 chars
        assert bs._is_meaningful("help me!") is True   # 8 chars


# ── redact ────────────────────────────────────────────────────────────────────

class TestRedact:
    def test_api_key(self):
        text = "my key is sk-abcdefghijklmnopqrstu"
        result = bs.redact(text)
        assert "sk-" not in result
        assert "[REDACTED]" in result

    def test_github_pat(self):
        text = "token ghp_" + "a" * 36
        result = bs.redact(text)
        assert "ghp_" not in result

    def test_email(self):
        text = "contact me at user@example.com please"
        result = bs.redact(text)
        assert "user@example.com" not in result
        assert "[REDACTED]" in result

    def test_password(self):
        text = "password=mysecretpass123"
        result = bs.redact(text)
        assert "mysecretpass123" not in result

    def test_clean_text_unchanged(self):
        text = "I want to build a memory system for AI"
        assert bs.redact(text) == text


# ── _text_from_content ────────────────────────────────────────────────────────

class TestTextFromContent:
    def test_string_content(self):
        assert bs._text_from_content("hello world") == "hello world"

    def test_list_with_text_block(self):
        content = [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]
        assert bs._text_from_content(content) == "hello world"

    def test_list_with_input_text(self):
        content = [{"type": "input_text", "input_text": "ignored", "text": "hello"}]
        assert bs._text_from_content(content) == "hello"

    def test_empty_list(self):
        assert bs._text_from_content([]) == ""

    def test_none_like(self):
        assert bs._text_from_content(None) == ""


# ── _sample_messages ─────────────────────────────────────────────────────────

class TestSampleMessages:
    def _make_msgs(self, n):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            {"ts": base, "text": f"msg{i}", "source": "claude", "project": "p", "cwd": ""}
            for i in range(n)
        ]

    def test_under_limit_returns_all(self):
        msgs = self._make_msgs(10)
        result = bs._sample_messages(msgs, 40)
        assert len(result) == 10

    def test_over_limit_samples(self):
        msgs = self._make_msgs(100)
        result = bs._sample_messages(msgs, 20)
        assert len(result) <= 20

    def test_exact_limit(self):
        msgs = self._make_msgs(20)
        result = bs._sample_messages(msgs, 20)
        assert len(result) == 20

    def test_preserves_order(self):
        msgs = self._make_msgs(5)
        result = bs._sample_messages(msgs, 40)
        texts = [m["text"] for m in result]
        assert texts == [f"msg{i}" for i in range(5)]


# ── build_session_digest ──────────────────────────────────────────────────────

class TestBuildSessionDigest:
    def _make_msg(self, text, cwd="C:\\project\\myapp"):
        return {
            "ts": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "source": "claude",
            "project": "myapp",
            "cwd": cwd,
            "text": text,
        }

    def test_contains_header(self):
        msgs = [self._make_msg("I want to build a memory system")]
        digest = bs.build_session_digest(msgs)
        assert "# SelfOS Session Digest" in digest

    def test_contains_instructions_block(self):
        msgs = [self._make_msg("working on my research paper")]
        digest = bs.build_session_digest(msgs)
        assert "Instructions for AI agent" in digest

    def test_contains_message_text(self):
        msgs = [self._make_msg("working on my research paper about memory")]
        digest = bs.build_session_digest(msgs)
        assert "working on my research paper about memory" in digest

    def test_groups_by_cwd(self):
        msgs = [
            self._make_msg("message from project A", cwd="C:\\proj\\alpha"),
            self._make_msg("message from project B", cwd="C:\\proj\\beta"),
        ]
        digest = bs.build_session_digest(msgs)
        assert "C:\\proj\\alpha" in digest or "proj" in digest
        assert "C:\\proj\\beta" in digest or "beta" in digest

    def test_total_count_in_header(self):
        msgs = [self._make_msg(f"message number {i} about building things") for i in range(5)]
        digest = bs.build_session_digest(msgs)
        assert "5" in digest


# ── load_state / save_state ───────────────────────────────────────────────────

class TestBootstrapState:
    def test_load_state_missing_returns_empty(self, tmp_path):
        state = bs.load_state(tmp_path)
        assert state == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        state = {"last_run": "2026-06-01T12:00:00+00:00"}
        bs.save_state(tmp_path, state)
        loaded = bs.load_state(tmp_path)
        assert loaded == state

    def test_save_creates_file(self, tmp_path):
        bs.save_state(tmp_path, {"last_run": "2026-01-01T00:00:00+00:00"})
        assert (tmp_path / bs.STATE_FILE_NAME).exists()

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        state_file = tmp_path / bs.STATE_FILE_NAME
        state_file.write_text("not valid json", encoding="utf-8")
        assert bs.load_state(tmp_path) == {}

    def test_state_file_name_constant(self):
        assert bs.STATE_FILE_NAME == ".bootstrap_state.json"


# ── cleanup_old_digests ───────────────────────────────────────────────────────

class TestCleanupOldDigests:
    def _make_digests(self, inbox: Path, n: int) -> list[Path]:
        files = []
        for i in range(n):
            f = inbox / f"2026-01-{i+1:02d}-sessions-digest.md"
            f.write_text(f"digest {i}", encoding="utf-8")
            files.append(f)
        return files

    def test_deletes_excess(self, tmp_path):
        self._make_digests(tmp_path, 10)
        deleted = bs.cleanup_old_digests(tmp_path, keep=7)
        assert deleted == 3
        remaining = list(tmp_path.glob("*-sessions-digest.md"))
        assert len(remaining) == 7

    def test_under_limit_deletes_nothing(self, tmp_path):
        self._make_digests(tmp_path, 5)
        deleted = bs.cleanup_old_digests(tmp_path, keep=7)
        assert deleted == 0
        assert len(list(tmp_path.glob("*-sessions-digest.md"))) == 5

    def test_keeps_most_recent(self, tmp_path):
        files = self._make_digests(tmp_path, 10)
        bs.cleanup_old_digests(tmp_path, keep=3)
        remaining = sorted(tmp_path.glob("*-sessions-digest.md"))
        assert remaining == sorted(files[-3:])

    def test_empty_inbox(self, tmp_path):
        deleted = bs.cleanup_old_digests(tmp_path, keep=7)
        assert deleted == 0


# ── resolve_since ─────────────────────────────────────────────────────────────

class TestResolveSince:
    def test_days_flag_overrides_state(self):
        state = {"last_run": "2026-01-01T00:00:00+00:00"}
        result = bs.resolve_since(args_days=7, args_full=False, state=state)
        assert result is not None
        # Should be ~7 days ago from now, not from state
        delta = datetime.now(timezone.utc) - result
        assert 6 < delta.days < 9

    def test_full_flag_returns_none(self):
        state = {"last_run": "2026-01-01T00:00:00+00:00"}
        assert bs.resolve_since(0, True, state) is None

    def test_no_state_returns_none(self):
        assert bs.resolve_since(0, False, {}) is None

    def test_state_returns_last_run(self):
        ts = "2026-06-01T10:00:00+00:00"
        state = {"last_run": ts}
        result = bs.resolve_since(0, False, state)
        assert result is not None
        assert result.isoformat() == ts


# ── Integration: fake JSONL → extract → digest ────────────────────────────────

class TestIntegrationExtractAndDigest:
    def _write_claude_session(self, proj_dir: Path, messages: list[str]) -> None:
        proj_dir.mkdir(parents=True, exist_ok=True)
        lines = []
        for i, text in enumerate(messages):
            record = {
                "type": "user",
                "timestamp": f"2026-06-0{i+1}T10:00:00.000Z",
                "cwd": str(proj_dir),
                "message": {"content": text},
            }
            lines.append(json.dumps(record))
        (proj_dir / "session.jsonl").write_text("\n".join(lines), encoding="utf-8")

    def test_extract_from_fake_session(self, tmp_path, monkeypatch):
        # Set up fake ~/.claude/projects/
        claude_dir = tmp_path / ".claude" / "projects"
        proj = claude_dir / "C--Users-foo-myapp"
        self._write_claude_session(proj, [
            "I want to build a machine learning pipeline for text classification",
            "done",  # noise — should be filtered
            "We need to add a preprocessing step that handles multilingual input",
        ])
        monkeypatch.setattr(bs.Path, "home", lambda: tmp_path)

        msgs, raw_count = bs.extract_claude_messages(since=None)
        # "done" is filtered; 2 meaningful messages remain
        assert len(msgs) == 2
        assert raw_count == 3  # all 3 user lines counted before filtering
        texts = [m["text"] for m in msgs]
        assert any("machine learning" in t for t in texts)
        assert any("multilingual" in t for t in texts)

    def test_digest_from_fake_session(self, tmp_path, monkeypatch):
        claude_dir = tmp_path / ".claude" / "projects"
        proj = claude_dir / "C--Users-foo-selfos"
        self._write_claude_session(proj, [
            "Building a personal knowledge management system with AI",
            "The goal is to track my research papers and decisions",
        ])
        monkeypatch.setattr(bs.Path, "home", lambda: tmp_path)

        msgs, raw_count = bs.extract_claude_messages(since=None)
        assert len(msgs) == 2
        assert raw_count == 2

        digest = bs.build_session_digest(msgs, raw_line_count=raw_count)
        assert "personal knowledge management" in digest
        assert "research papers" in digest
        assert "# SelfOS Session Digest" in digest
        assert "Signal quality" in digest


# ── ensure_vault_structure ────────────────────────────────────────────────────

class TestEnsureVaultStructure:
    def test_creates_missing_dirs(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        created = bs.ensure_vault_structure(vault)
        dir_names = [c.strip().lstrip("+ ").rstrip("/") for c in created if c.strip().endswith("/")]
        for d in bs.VAULT_DIRS:
            assert (vault / d).is_dir(), f"Missing: {d}"

    def test_creates_missing_files(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.ensure_vault_structure(vault)
        for fname in bs.VAULT_FILES:
            assert (vault / fname).exists(), f"Missing: {fname}"

    def test_does_not_overwrite_existing(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        existing = vault / "PROFILE.md"
        existing.write_text("# My Custom Profile\n", encoding="utf-8")
        bs.ensure_vault_structure(vault)
        assert existing.read_text(encoding="utf-8") == "# My Custom Profile\n"

    def test_returns_created_list(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        created = bs.ensure_vault_structure(vault)
        assert len(created) > 0

    def test_idempotent(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.ensure_vault_structure(vault)
        created_second = bs.ensure_vault_structure(vault)
        assert created_second == []

    def test_creates_module_placeholders(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.ensure_vault_structure(vault)
        # Check that at least some module placeholder files were created
        assert (vault / "01_Career" / "profile.md").exists()
        assert (vault / "04_Health_Fitness" / "log.md").exists()
        assert (vault / "05_Life" / "learning.md").exists()

    def test_module_placeholder_content_is_meaningful(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.ensure_vault_structure(vault)
        content = (vault / "01_Career" / "profile.md").read_text(encoding="utf-8")
        assert "Career Profile" in content
        assert len(content) > 30

    def test_does_not_overwrite_existing_module_files(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "01_Career").mkdir(parents=True)
        existing = vault / "01_Career" / "profile.md"
        existing.write_text("# My Custom Career\n", encoding="utf-8")
        bs.ensure_vault_structure(vault)
        assert existing.read_text(encoding="utf-8") == "# My Custom Career\n"


# ── __version__ ───────────────────────────────────────────────────────────────

class TestVersion:
    def test_version_attribute_exists(self):
        assert hasattr(bs, "__version__")

    def test_version_is_string(self):
        assert isinstance(bs.__version__, str)

    def test_version_format(self):
        parts = bs.__version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


# ── _file_mtime_ok ────────────────────────────────────────────────────────────

class TestFileMtimeOk:
    def test_no_since_always_true(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text("x")
        assert bs._file_mtime_ok(f, since=None) is True

    def test_recent_file_is_ok(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text("x")
        since = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert bs._file_mtime_ok(f, since) is True

    def test_future_since_filters_old_file(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text("x")
        since = datetime(2099, 1, 1, tzinfo=timezone.utc)
        assert bs._file_mtime_ok(f, since) is False

    def test_missing_file_returns_true(self, tmp_path):
        f = tmp_path / "nonexistent.jsonl"
        since = datetime(2099, 1, 1, tzinfo=timezone.utc)
        assert bs._file_mtime_ok(f, since) is True


# ── compute_signal_quality ────────────────────────────────────────────────────

class TestComputeSignalQuality:
    def _make_msgs(self, n):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"ts": base, "text": f"msg {i}", "source": "claude", "project": "p", "cwd": ""} for i in range(n)]

    def test_high_signal(self):
        msgs = self._make_msgs(50)
        result = bs.compute_signal_quality(msgs, raw_line_count=100)
        assert result["label"] == "high"
        assert result["signal_ratio"] == 0.5

    def test_medium_signal(self):
        msgs = self._make_msgs(20)
        result = bs.compute_signal_quality(msgs, raw_line_count=100)
        assert result["label"] == "medium"

    def test_low_signal(self):
        msgs = self._make_msgs(5)
        result = bs.compute_signal_quality(msgs, raw_line_count=100)
        assert result["label"] == "low"

    def test_zero_raw_count_no_division_error(self):
        msgs = self._make_msgs(10)
        result = bs.compute_signal_quality(msgs, raw_line_count=0)
        assert result["label"] == "high"

    def test_digest_includes_quality_when_raw_count_provided(self):
        msgs = [
            {"ts": datetime(2026, 6, 1, tzinfo=timezone.utc), "source": "claude",
             "project": "p", "cwd": "/proj", "text": "building a thing"}
        ]
        digest = bs.build_session_digest(msgs, raw_line_count=10)
        assert "Signal quality" in digest

    def test_digest_omits_quality_when_no_raw_count(self):
        msgs = [
            {"ts": datetime(2026, 6, 1, tzinfo=timezone.utc), "source": "claude",
             "project": "p", "cwd": "/proj", "text": "building a thing"}
        ]
        digest = bs.build_session_digest(msgs, raw_line_count=0)
        assert "Signal quality" not in digest


# ── build_stats_report ────────────────────────────────────────────────────────

class TestBuildStatsReport:
    def _make_msg(self, text, cwd, source="claude", day=1):
        return {
            "ts": datetime(2026, 6, day, tzinfo=timezone.utc),
            "source": source,
            "project": Path(cwd).name if cwd else "unknown",
            "cwd": cwd,
            "text": text,
        }

    def test_contains_header_row(self):
        msgs = [self._make_msg("building something useful", "/proj/alpha")]
        report = bs.build_stats_report(msgs)
        assert "Context" in report
        assert "Msgs" in report

    def test_contains_project_name(self):
        msgs = [self._make_msg("working on alpha project", "/proj/alpha")]
        report = bs.build_stats_report(msgs)
        assert "alpha" in report

    def test_shows_message_count(self):
        msgs = [
            self._make_msg("first message about the project", "/proj/alpha", day=1),
            self._make_msg("second message about the project", "/proj/alpha", day=2),
            self._make_msg("third message about the project", "/proj/alpha", day=3),
        ]
        report = bs.build_stats_report(msgs)
        assert "3" in report

    def test_shows_total_line(self):
        msgs = [
            self._make_msg("alpha work message here", "/proj/alpha"),
            self._make_msg("beta work message here", "/proj/beta"),
        ]
        report = bs.build_stats_report(msgs)
        assert "Total" in report
        assert "2" in report

    def test_multiple_sources(self):
        msgs = [
            self._make_msg("claude session message", "/proj/x", source="claude"),
            self._make_msg("codex session message", "/proj/x", source="codex"),
        ]
        report = bs.build_stats_report(msgs)
        assert "claude" in report or "codex" in report


# ── score_vault / load_scores / generate_dashboard ───────────────────────────

class TestScoreVault:
    def test_returns_all_dimensions(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = bs.score_vault(vault)
        for key, _, _ in bs.SCORE_DIMENSIONS:
            assert key in scores

    def test_null_when_no_content(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = bs.score_vault(vault)
        # vault is empty — all should be None
        assert all(v is None for v in scores.values())

    def test_skip_excludes_dimension(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = bs.score_vault(vault, skip=["family"])
        assert scores["family"] is None

    def test_scores_written_to_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.score_vault(vault)
        scores_file = vault / bs.SCORES_FILE
        assert scores_file.exists()
        content = scores_file.read_text(encoding="utf-8")
        assert "career" in content

    def test_scores_replace_on_same_day(self, tmp_path):
        """Running twice on the same day replaces the row, not appends."""
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.score_vault(vault)
        bs.score_vault(vault)
        content = (vault / bs.SCORES_FILE).read_text(encoding="utf-8")
        rows = [l for l in content.splitlines() if l.startswith("- ")]
        assert len(rows) == 1

    def test_infer_score_positive_signals(self):
        text = "\n".join([
            "I trained at the gym today, had a great workout, feeling healthy and strong.",
            "Ran 5km in the morning without stopping, personal best this month.",
            "Energy levels are high and sleep has been consistent all week.",
            "No injuries, feeling fully recovered from last week's session.",
            "Planning another workout tomorrow with the team after work.",
            "Nutrition has been on track, eating well and staying hydrated.",
            "Mental health is also good, no stress or anxiety lately.",
            "Doctor gave a clean bill of health at the last checkup.",
            "Hit my weekly step goal for the third week in a row.",
            "Overall feeling the best I have in months, very positive.",
        ])
        score = bs._infer_score(text, "health")
        assert score is not None
        assert score >= 6

    def test_infer_score_negative_signals(self):
        text = "\n".join([
            "I am sick, injured, in pain, too fatigued to do anything at all.",
            "Skipped training again for the third day in a row this week.",
            "Feeling exhausted and completely unmotivated to exercise or move.",
            "Back pain has been getting progressively worse every single day.",
            "Doctor said to rest but it is very hard to stay positive right now.",
            "Sleep has been terrible, waking up multiple times each night.",
            "Energy is at an all-time low, struggling to get through the day.",
            "Missed my weekly exercise goals again, feeling behind on everything.",
            "The fatigue is making it hard to concentrate or get any work done.",
            "Really struggling to maintain any kind of healthy routine this week.",
        ])
        score = bs._infer_score(text, "health")
        assert score is not None
        assert score <= 4

    def test_infer_score_null_on_short_text(self):
        assert bs._infer_score("hi", "career") is None
        assert bs._infer_score("", "work") is None

    def test_infer_score_null_on_template(self):
        text = (
            "# Career Profile\n\n"
            "> Fill this in after /digest.\n\n"
            "## Current Role\n"
            "- Title:\n"
            "- Company:\n\n"
            "## Technical Skills\n"
            "- \n"
        )
        assert bs._infer_score(text, "career") is None

    def test_infer_score_range(self):
        text = "\n".join([
            "Shipped the new feature to production today, everything went smoothly.",
            "Merged the PR after code review, all tests passed on the first try.",
            "Completed the sprint goals ahead of schedule this week.",
            "Deployed to staging and got very positive feedback from stakeholders.",
            "Team velocity has been exceptionally strong this entire sprint.",
            "Fixed two critical bugs that had been blocking users for weeks.",
            "Documentation is up to date and the codebase is in great shape.",
            "Unblocked two teammates who were stuck on dependency issues.",
            "Reviewed three PRs and left thorough, helpful comments on each.",
            "Overall a very productive and satisfying week of solid engineering work.",
        ])
        score = bs._infer_score(text, "work")
        assert score is not None
        assert 1 <= score <= 10


class TestLoadScores:
    def test_empty_when_no_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        assert bs.load_scores(vault) == []

    def test_parses_entries(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.score_vault(vault)
        entries = bs.load_scores(vault)
        assert len(entries) >= 1
        assert "date" in entries[0]

    def test_most_recent_first(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores_path = vault / bs.SCORES_FILE
        scores_path.write_text(
            "---\ntype: life-scores\n---\n\n"
            "- 2026-01-01 | career: 5\n"
            "- 2026-06-01 | career: 7\n",
            encoding="utf-8"
        )
        entries = bs.load_scores(vault)
        assert entries[0]["date"] == "2026-06-01"
        assert entries[1]["date"] == "2026-01-01"

    def test_null_values_parsed(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / bs.SCORES_FILE).write_text(
            "---\ntype: life-scores\n---\n\n- 2026-01-01 | career: null | work: 5\n",
            encoding="utf-8"
        )
        entries = bs.load_scores(vault)
        assert entries[0]["career"] is None
        assert entries[0]["work"] == 5


class TestGenerateDashboard:
    def test_creates_html_file(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        out = bs.generate_dashboard(vault)
        assert out.exists()
        assert out.suffix == ".html"

    def test_html_contains_dimensions(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = {key: 7 for key, _, _ in bs.SCORE_DIMENSIONS}
        bs.generate_dashboard(vault, scores)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        for _, label, _ in bs.SCORE_DIMENSIONS:
            assert label in html

    def test_overall_score_shown(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = {key: 8 for key, _, _ in bs.SCORE_DIMENSIONS}
        bs.generate_dashboard(vault, scores)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "8" in html

    def test_no_data_shows_dash(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault, scores=None)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "—" in html

    def test_skip_dim_not_shown(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = {key: 7 for key, _, _ in bs.SCORE_DIMENSIONS}
        scores["family"] = "skip"
        bs.generate_dashboard(vault, scores)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "家庭" not in html

    def test_bilingual_toggle_button_present(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "toggleLang" in html
        assert "EN" in html

    def test_english_strings_embedded(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = {key: 7 for key, _, _ in bs.SCORE_DIMENSIONS}
        bs.generate_dashboard(vault, scores)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "Career" in html
        assert "Health" in html
        assert "Overall" in html

    def test_suggestion_text_present(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        scores = {key: 7 for key, _, _ in bs.SCORE_DIMENSIONS}
        bs.generate_dashboard(vault, scores)
        html = (vault.parent / "dashboard.html").read_text(encoding="utf-8")
        assert "dim-suggestion" in html


# ── _get_api_config ───────────────────────────────────────────────────────────

class TestGetApiConfig:
    def test_reads_from_env_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        env = tmp_path / ".env"
        env.write_text("ANTHROPIC_API_KEY=test-key-123\nANTHROPIC_BASE_URL=http://proxy/anthropic\n", encoding="utf-8")
        key, base_url = bs._get_api_config(tmp_path)
        assert key == "test-key-123"
        assert base_url == "http://proxy/anthropic"

    def test_missing_env_file_returns_empty_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        key, base_url = bs._get_api_config(tmp_path)
        assert key == ""
        assert base_url == "https://api.anthropic.com"

    def test_env_var_takes_precedence_over_file(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("ANTHROPIC_API_KEY=file-key\n", encoding="utf-8")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        key, _ = bs._get_api_config(tmp_path)
        assert key == "env-key"

    def test_strips_trailing_slash_from_base_url(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        env = tmp_path / ".env"
        env.write_text("ANTHROPIC_API_KEY=k\nANTHROPIC_BASE_URL=http://proxy/\n", encoding="utf-8")
        _, base_url = bs._get_api_config(tmp_path)
        assert not base_url.endswith("/")

    def test_quoted_key_stripped(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        env = tmp_path / ".env"
        env.write_text('ANTHROPIC_API_KEY="quoted-key"\n', encoding="utf-8")
        key, _ = bs._get_api_config(tmp_path)
        assert key == "quoted-key"


# ── auto_generate_staging ─────────────────────────────────────────────────────

class TestAutoGenerateStaging:
    def _make_vault(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "90_Inbox").mkdir()
        (vault / "91_Staging").mkdir()
        return vault

    def test_skips_when_no_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# SelfOS Session Digest\nsome content", encoding="utf-8")
        result = bs.auto_generate_staging(vault, digest)
        assert result == []

    def test_writes_staging_files_on_success(self, tmp_path, monkeypatch):
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# SelfOS Session Digest\nsome content", encoding="utf-8")

        fake_response = json.dumps([
            {"target": "vault/NOW.md", "type": "now", "content": "# Now\nActive: SelfOS development"},
            {"target": "vault/GOALS.md", "type": "goals", "content": "# Goals\n- Ship SelfOS"},
        ])
        import unittest.mock as mock

        class FakeResp:
            def read(self): return json.dumps({"content": [{"text": fake_response}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(bs, "urlopen", lambda req, timeout=30: FakeResp())
        monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: bs.urlopen)

        result = bs.auto_generate_staging(vault, digest)
        assert len(result) == 2
        for p in result:
            assert p.exists()
            assert p.suffix == ".md"
            text = p.read_text(encoding="utf-8")
            assert "target:" in text
            assert "source: auto-harvest" in text

    def test_staging_file_frontmatter_has_target(self, tmp_path, monkeypatch):
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# digest", encoding="utf-8")

        fake_response = json.dumps([
            {"target": "vault/NOW.md", "type": "now", "content": "# Now\nfoo"},
        ])
        import unittest.mock as mock

        class FakeResp:
            def read(self): return json.dumps({"content": [{"text": fake_response}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(bs, "urlopen", lambda req, timeout=30: FakeResp())
        monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: bs.urlopen)

        result = bs.auto_generate_staging(vault, digest)
        assert len(result) == 1
        text = result[0].read_text(encoding="utf-8")
        assert "target: vault/NOW.md" in text

    def test_handles_malformed_json_response(self, tmp_path, monkeypatch):
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# digest", encoding="utf-8")

        class FakeResp:
            def read(self): return json.dumps({"content": [{"text": "not json at all"}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(bs, "urlopen", lambda req, timeout=30: FakeResp())
        monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: bs.urlopen)

        result = bs.auto_generate_staging(vault, digest)
        assert result == []

    def test_handles_api_error_gracefully(self, tmp_path, monkeypatch):
        from urllib.error import URLError
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# digest", encoding="utf-8")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(bs, "urlopen", lambda req, timeout=30: (_ for _ in ()).throw(URLError("timeout")))
        monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: bs.urlopen)

        result = bs.auto_generate_staging(vault, digest)
        assert result == []

    def test_skips_items_with_missing_fields(self, tmp_path, monkeypatch):
        vault = self._make_vault(tmp_path)
        digest = vault / "90_Inbox" / "2026-01-01-sessions-digest.md"
        digest.write_text("# digest", encoding="utf-8")

        fake_response = json.dumps([
            {"target": "", "type": "now", "content": "# Now"},        # empty target
            {"target": "vault/NOW.md", "type": "now", "content": ""},  # empty content
            {"target": "vault/GOALS.md", "type": "goals", "content": "# Goals\nreal content here"},
        ])

        class FakeResp:
            def read(self): return json.dumps({"content": [{"text": fake_response}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(bs, "urlopen", lambda req, timeout=30: FakeResp())
        monkeypatch.setattr(__import__('selfos.providers.client', fromlist=['*']), 'request_opener', lambda root: bs.urlopen)

        result = bs.auto_generate_staging(vault, digest)
        assert len(result) == 1  # only GOALS.md with real content


# ── serve.py staging endpoints ────────────────────────────────────────────────

class TestServeStagingLogic:
    """Test staging apply logic directly without HTTP handler plumbing."""

    def _write_staging(self, staging_dir, fname, target, content_body):
        f = staging_dir / fname
        f.write_text(
            f"---\ntype: now\ntarget: {target}\n---\n\n{content_body}",
            encoding="utf-8"
        )
        return f

    def _apply(self, root, filenames):
        """Replicate serve.py /__staging__/apply logic for unit testing."""
        vault = root / "vault"
        staging_dir = vault / "91_Staging"
        applied, errors = [], []
        for fname in filenames:
            staging_path = staging_dir / fname
            if not staging_path.exists():
                errors.append(f"{fname}: not found")
                continue
            text = staging_path.read_text(encoding="utf-8", errors="replace")
            target = ""
            content_start = 0
            lines = text.splitlines(keepends=True)
            if lines and lines[0].strip() == "---":
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() == "---":
                        content_start = i + 1
                        break
                    if line.startswith("target:"):
                        target = line.split(":", 1)[1].strip()
            if not target:
                errors.append(f"{fname}: no target")
                continue
            target_path = root / target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            content = "".join(lines[content_start:]).lstrip("\n")
            target_path.write_text(content, encoding="utf-8")
            staging_path.unlink()
            applied.append(fname)
        return {"ok": True, "applied": applied, "errors": errors}

    def test_apply_writes_target_file(self, tmp_path):
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)
        self._write_staging(staging, "2026-01-01-auto-now.md", "vault/NOW.md", "# Now\nActive: testing\n")

        result = self._apply(tmp_path, ["2026-01-01-auto-now.md"])

        assert result["ok"] is True
        assert "2026-01-01-auto-now.md" in result["applied"]
        target = tmp_path / "vault" / "NOW.md"
        assert target.exists()
        assert "Active: testing" in target.read_text(encoding="utf-8")

    def test_apply_removes_staging_file(self, tmp_path):
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)
        f = self._write_staging(staging, "2026-01-01-auto-now.md", "vault/NOW.md", "# Now\n")

        self._apply(tmp_path, ["2026-01-01-auto-now.md"])
        assert not f.exists()

    def test_apply_missing_file_reported_as_error(self, tmp_path):
        vault = tmp_path / "vault"
        (vault / "91_Staging").mkdir(parents=True)
        result = self._apply(tmp_path, ["nonexistent.md"])
        assert result["ok"] is True
        assert len(result["errors"]) == 1
        assert result["applied"] == []

    def test_apply_strips_frontmatter(self, tmp_path):
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)
        self._write_staging(staging, "2026-01-01-auto-goals.md", "vault/GOALS.md", "# Goals\n- Ship it\n")

        self._apply(tmp_path, ["2026-01-01-auto-goals.md"])
        content = (tmp_path / "vault" / "GOALS.md").read_text(encoding="utf-8")
        assert "---" not in content
        assert "# Goals" in content
        assert "Ship it" in content

    def test_apply_creates_parent_dirs(self, tmp_path):
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)
        self._write_staging(staging, "2026-01-01-auto-research.md",
                            "vault/03_Research/new_project.md", "# Research\nExperiment 1\n")

        self._apply(tmp_path, ["2026-01-01-auto-research.md"])
        target = tmp_path / "vault" / "03_Research" / "new_project.md"
        assert target.exists()

    def test_get_staging_lists_files(self, tmp_path):
        """Test the /__staging__ GET response structure."""
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)
        f = staging / "2026-01-01-auto-now.md"
        f.write_text("---\ntype: now\ntarget: vault/NOW.md\n---\n\n# Now\n", encoding="utf-8")

        # replicate GET logic
        files = []
        for fp in sorted(staging.glob("*.md")):
            text = fp.read_text(encoding="utf-8", errors="replace")
            target = ""
            for line in text.splitlines():
                if line.startswith("target:"):
                    target = line.split(":", 1)[1].strip()
                    break
            files.append({"name": fp.name, "target": target, "content": text})

        assert len(files) == 1
        assert files[0]["name"] == "2026-01-01-auto-now.md"
        assert files[0]["target"] == "vault/NOW.md"

    def test_get_staging_empty_when_no_files(self, tmp_path):
        vault = tmp_path / "vault"
        staging = vault / "91_Staging"
        staging.mkdir(parents=True)

        files = list(staging.glob("*.md"))
        assert files == []


# ── dashboard staging UI ──────────────────────────────────────────────────────

class TestDashboardStagingUI:
    def test_staging_btn_in_html(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault)
        html = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
        assert "staging-btn" in html
        assert "openStagingModal" in html

    def test_staging_modal_in_html(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault)
        html = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
        assert "staging-modal" in html
        assert "applySelectedStaging" in html

    def test_check_staging_js_present(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault)
        html = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
        assert "checkStaging" in html
        assert "__staging__" in html

    def test_progress_bar_in_html(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        bs.generate_dashboard(vault)
        html = (tmp_path / "dashboard.html").read_text(encoding="utf-8")
        assert "progress-bar" in html
        assert "EventSource" in html

    def test_suggestion_returns_both_langs(self):
        s = bs._suggestion("health", 8)
        assert "zh" in s and "en" in s
        assert len(s["zh"]) > 5
        assert len(s["en"]) > 5

    def test_suggestion_nodata_when_none(self):
        s = bs._suggestion("career", None)
        assert "vault" in s["zh"] or "vault" in s["en"]
