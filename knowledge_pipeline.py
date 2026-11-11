"""Compact conversations into sourced project state; serialize all vault writes."""
import copy
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import base64
import threading
import uuid
from urllib.error import HTTPError
from harvest import redact
from functools import lru_cache
SYNTHESIS_VERSION = 12


def api_summarizer(root, *, review_records=True):
    """Published prepared-session adapter used by the frozen live evaluation."""
    from knowledge import api_summarizer as factory
    return factory(root,review_records=review_records)


def import_runtime_line(line):
    return bool(re.fullmatch(
        r'(?:SelfOS Knowledge: scanning local Claude Code and Codex conversations|'
        r'Scanned \d+ messages; compacted into \d+ session parts|'
        r'Knowledge: \d+ (?:messages, \d+ new batches|compact session parts, \d+ pending; workers \d+)|'
        r'Organizing (?:session|batch) \d+/\d+ \.\.\.|'
        r'Saved (?:session|batch) \d+/\d+(?:: \d+ facts)?; backup [A-Za-z0-9_-]+|'
        r'(?:Session|Batch) \d+, attempt \d+/\d+:.*|'
        r'Knowledge import failed:.*|Diagnostic: vault/\.knowledge_errors/.*|'
        r'Retrying generation with the validation error as repair feedback \.\.\.|'
        r'Batch not saved; completed earlier batches are preserved\. Retry remains available\.)',line.strip()))


def content_identity(message):
    if message.get("provenance") in ("quoted_dialogue","runtime_evidence","runtime_output","machine_summary","agent_status"):
        return message["provenance"]
    text = message.get("text", "").strip()
    if text and all(import_runtime_line(line) for line in text.splitlines() if line.strip()):
        return "runtime_output"
    head = text[:800]
    if head.startswith('<codex_internal_context') and text.endswith('</codex_internal_context>'):
        return 'machine_summary'
    if any(t in head for t in ("<local-command-stdout>", "<local-command-caveat>", "[external_agent_tool_result]")):
        return "runtime_output"
    if head.startswith(("This session is being continued from a previous conversation",
                        "Another language model started to solve this problem", "# Update Config Skill",
                        "Base directory for this skill:")):
        return "machine_summary"
    if any(t in head for t in ("当前子代理没有可调用的文件读取", "Agent errored: stream disconnected", "本次未完成有效审查")):
        return "agent_status"
    if message.get("provenance") == "quoted_dialogue" or (message.get("role") == "user" and (
        any(t in head for t in ("以下是之前 AI", "以下是AI", "GPT回答", "DeepSeek回答", "个人健身档案整理")) or
        (len(text) > 12000 and any(t in text for t in ("把这部分抽取", "ChatGPT", "DeepSeek", "用户：", "Assistant:"))))):
        return "quoted_dialogue"
    return "user_statement" if message.get("role") == "user" else "assistant_suggestion"


@lru_cache(maxsize=512)
def canonical_project(identity):
    path = Path(identity)
    if not path.is_dir():
        return identity
    for parent in (path, *path.parents):
        git = parent / ".git"
        if git.is_dir():
            return str(parent).replace(chr(92), "/")
        if git.is_file():
            content = git.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                gitdir = (parent / content[7:].strip()).resolve()
                common = gitdir / "commondir"
                if common.exists():
                    directory = (gitdir / common.read_text().strip()).resolve()
                    return str(directory.parent if directory.name == ".git" else directory).replace(chr(92), "/")
            return str(parent).replace(chr(92), "/")
    return identity


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def transient_only(text):
    transient = {'继续','再跑一次','好的','谢谢','取消这次运行','先停一下','重试','帮我打开终端',
                 'continue','retry','run it again','thanks','ok','stop this run','open the terminal',
                 '/clear','/exit','git status','对','yes','好的，谢谢','ping',
                 '现在进行到哪里了','现在什么情况','怎么样了，可以继续吗','什么情况了'}
    normalized=text.strip().casefold().rstrip('.!。！？?')
    if normalized in transient:return True
    parts=[part.strip() for part in re.split(r'[.!。！？?;；,，]+',normalized.replace(chr(10),';')) if part.strip()]
    return bool(parts) and all(part in transient for part in parts)


def compact_message(message):
    if message.get("role") == "tool" and not message.get("verification", {}).get("relevant"):
        return None
    text = redact(message["text"]).strip()
    provenance = content_identity(message)
    if provenance in ("runtime_output", "machine_summary", "agent_status"):
        if not message.get("verification", {}).get("relevant"):
            evidence = unique(line.strip()[:400] for line in text.splitlines() if re.search(
                r"FAILED\s+test_|(?:ValueError|RuntimeError|AssertionError|TimeoutError):|"
                r"^(?:Session|Batch) \d+, attempt \d+/\d+:|^Knowledge import failed:", line))[:8]
            if provenance != "runtime_output" or not evidence:
                return None
            text = "Runtime failure evidence (not a user statement):\n" + "\n".join(evidence)
            provenance = "runtime_evidence"
    if transient_only(text):
        return None
    def code(match):
        body = match.group(1)
        symbols = re.findall(r"(?:def|function|class|CREATE TABLE|void)\s+([A-Za-z_][\w]*)", body, re.I)
        return "[Code omitted; symbols: " + ", ".join(dict.fromkeys(symbols))[:600] + "]"
    text = re.sub(r"```[^\n]*\n(.*?)```", code, text, flags=re.S)
    # Parse complete bulk JSON documents, retaining surrounding purpose and outcome prose.
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text):
        match = re.search(r"[\[{]", text[position:])
        if not match:
            break
        start = position + match.start()
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            position = start + 1
            continue
        if end - start > 1200:
            keys = list(value)[:12] if isinstance(value, dict) else list(value[0])[:12] if value and isinstance(value[0], dict) else []
            replacement = "[Bulk JSON omitted; fields: " + ", ".join(map(str, keys)) + "]"
            text = text[:start] + replacement + text[end:]
            position = start + len(replacement)
        else:
            position = end
    # Keep explanatory prose on both sides; do not truncate the outcome at the tail.
    lines = text.splitlines()
    failures = unique(re.sub(r"^\s*\d{4}-\d\d-\d\d\S*\s*", "", line.strip())[:300]
                      for line in lines if re.match(r"^\s*\d{4}-\d\d-\d\d", line) and
                      re.search(r"ERROR|FAILED|Exception|Error:", line))[:6]
    text = "\n".join(line for line in lines if not re.match(
        r"^\s*(?:\{\"|\d{4}-\d\d-\d\d[T ]|[+\-]\s*(?:const |import |def )|\s*at .*:\d+)", line)
        and (not import_runtime_line(line) or re.match(r'^(?:Session|Batch) \d+, attempt \d+/\d+:|^Knowledge import failed:',line)))
    text = text.strip()
    if failures:
        text += "\nFailure evidence:\n" + "\n".join(failures)
    if not text or re.fullmatch(r"\[Code omitted; symbols: .*\]", text):
        return None
    return {**copy.deepcopy(message), "text": text, "provenance": provenance}


def prepare_sessions(messages, max_chars=12000, cancel=lambda: False, aliases=None):
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    groups = defaultdict(dict)
    for raw in messages:
        if cancel():
            break
        m = compact_message(raw)
        if m is None:
            continue
        m["project_id"] = canonical_project(raw.get("project_id") or raw.get("project") or "unknown")
        if aliases:
            m["project_id"] = aliases.get(m["project_id"], m["project_id"])
        m["session_id"] = raw.get("session_id") or raw.get("path") or "unknown"
        groups[(m["project_id"], m["session_id"])].setdefault(m["id"], m)
    sessions = []
    for (project, session), records in sorted(groups.items()):
        if cancel():
            break
        parts, part, size = [], [], 0
        for m in sorted(records.values(), key=lambda x: (x.get("timestamp", ""), x["id"])):
            for offset in range(0, len(m["text"]), max_chars):
                piece = {**m, "text": m["text"][offset:offset + max_chars]}
                if part and size + len(piece["text"]) > max_chars:
                    parts.append(part)
                    part, size = [], 0
                part.append(piece)
                size += len(piece["text"])
        if part:
            parts.append(part)
        for index, part in enumerate(parts):
            sessions.append(dict(project_id=project, session_id=session, part=index, messages=part,
                                 fingerprint=digest(part)))
    return sessions


def unique(items):
    return list(dict.fromkeys(items))


def clean_actions(items):
    return [item for item in items if not re.match(
        r"^\s*(?:Call|Invoke|调用|执行)\s*(?:ScheduleWakeup|request_user_input_async|SendMessage|GetHandoffStatus)\b",item,re.I)]


def merge_project_card(current, update, limit=8):
    from knowledge_history import collect_state_records
    def lineage(card):
        if 'decision_records' in card:return copy.deepcopy(card['decision_records'])
        if 'decision_history' in card:return []  # Legacy aggregation has no per-session attribution.
        return [{'text':text,'source_ids':card.get('source_ids',[]),
                 'observed_at':card.get('updated_at',''),'source_scope':'session_context',
                 'domain':card.get('domain','work')}
                for text in card.get('decisions',[])]
    if current is None:
        result = copy.deepcopy(update)
        result['state_records']=collect_state_records([update])
        result['state_inputs']=collect_state_records([update],collapse=False)
        result['decision_records']=lineage(update)
        result["decision_history"] = unique(result.get("decision_history", result["decisions"]))
        result["decisions"] = result["decision_history"][-limit:]
        return result
    if current["project_id"] != update["project_id"]:
        raise ValueError("cross-project update")
    def order(card):
        return (card["updated_at"], *card.get("_order", ["", 0]))
    old, new = (current, update) if order(current) <= order(update) else (update, current)
    merged = copy.deepcopy(new)
    merged['state_records']=collect_state_records([current,update])
    merged['state_inputs']=collect_state_records([current,update],collapse=False)
    merged["intent"] = new.get("intent") or old.get("intent", "")
    merged["title"] = old.get("title") or new["title"]
    def state_order(card):
        if "_state_order" in card:
            return tuple(card["_state_order"]) if card["_state_order"] else None
        return order(card) if card.get("status") != "unknown" else None
    states = [(state_order(c), c) for c in (current, update) if state_order(c) is not None]
    if states:
        version, state = max(states, key=lambda pair: pair[0])
        for field in ("status", "blockers", "next_steps", "verified"):
            merged[field] = copy.deepcopy(state[field])
        merged["_state_order"] = list(version)
    merged["decision_history"] = unique(old.get("decision_history", old.get("decisions", [])) +
                                        new.get("decision_history", new.get("decisions", [])))
    merged["decisions"] = merged["decision_history"][-limit:]
    records={}
    for r in lineage(old)+lineage(new):
        key=(r['text'],r.get('domain','unclassified'))
        previous=records.get(key)
        if previous:
            previous['source_ids']=unique(previous['source_ids']+r['source_ids'])
            previous['observed_at']=max(previous.get('observed_at',''),r.get('observed_at',''))
        else:records[key]=copy.deepcopy(r)
    merged['decision_records']=list(records.values())
    merged["source_ids"] = unique(old.get("source_ids", []) + new.get("source_ids", []))
    return merged


def validate_summary(candidate, session, *, lesson_limit=12):
    if not isinstance(candidate, dict):
        raise ValueError("summary must be an object")
    result = copy.deepcopy(candidate)
    from knowledge_policy import validate_record
    for category in ('personal_facts','preferences','history'):
        records=result.get(category,[])
        if not isinstance(records,list) or len(records)>100:
            raise ValueError('Invalid '+category+' record array')
        validated_records=[]
        for index,record in enumerate(records):
            try:
                validated_records.append(validate_record(record,session))
            except ValueError as error:
                raise ValueError(f'{category}[{index}]: {error}') from error
        result[category]=validated_records
    card = result.get("project")
    if card is None and result.get("lessons") == []:
        return result
    if card is None and isinstance(result.get("lessons"), list):
        result["project"] = {"project_id": session["project_id"], "title":"", "intent":"",
            "status":"unknown", "decisions":[], "blockers":[], "next_steps":[],
            "updated_at":"", "source_ids": unique(m["id"] for m in session["messages"]), "verified":False}
        validated = validate_summary(result, session,lesson_limit=lesson_limit)
        validated["project"] = None
        return validated
    if not isinstance(card, dict) or card.get("project_id") != session["project_id"]:
        raise ValueError("summary project identity mismatch")
    known = {m["id"]: m for m in session["messages"]}
    def sources(item):
        ids = item.get("source_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in known for i in ids):
            raise ValueError("summary has untraceable sources")
        item["source_ids"] = unique(ids)
    sources(card)
    card['domain']=str(card.get('domain','work')).casefold()
    for field in ("title", "intent", "updated_at"):
        if not isinstance(card.get(field), str) or len(card[field]) > 2000:
            raise ValueError("invalid " + field)
        card[field] = redact(card[field])
    for field in ("decisions", "blockers", "next_steps"):
        if not isinstance(card.get(field), list) or len(card[field]) > 12 or any(not isinstance(v, str) or len(v) > 2000 for v in card[field]):
            raise ValueError("invalid " + field)
        card[field] = clean_actions([re.sub(r"\s*\(s\d+(?:\s*,\s*s\d+)*\)", "", redact(v)) for v in card[field]])
    if card.get("status") not in ("in_progress", "blocked", "paused", "completed", "reported_complete", "unknown"):
        raise ValueError("invalid status")
    evidence = [known[i].get("verification", {}) for i in card["source_ids"]]
    verified = any(e.get("relevant") is True and e.get("exit_code") == 0 for e in evidence)
    if any(e.get("relevant") is True and e.get("exit_code") != 0 for e in evidence):
        verified = False
    card["verified"] = verified if card["status"] == "completed" else False
    if card["status"] == "completed" and not verified:
        card["status"] = "reported_complete"
    # Model timestamps never supersede the actual conversation timestamps.
    card["updated_at"] = max(m.get("timestamp", "") for m in session["messages"])
    card["_order"] = [session["session_id"], session.get("part", 0)]
    card["_state_order"] = [card["updated_at"], *card["_order"]] if card["status"] != "unknown" else None
    lessons = result.get("lessons", [])
    if not isinstance(lessons, list) or (lesson_limit is not None and len(lessons) > lesson_limit):
        raise ValueError("invalid lessons")
    for lesson in lessons:
        if not isinstance(lesson, dict):
            raise ValueError("invalid lesson")
        sources(lesson)
        if not isinstance(lesson.get("text"), str) or not lesson["text"].strip() or len(lesson["text"]) > 2000:
            raise ValueError("invalid lesson text")
        if lesson.get("kind") not in ("user_fact", "assistant_suggestion", "inference"):
            raise ValueError("invalid lesson kind")
        if lesson["kind"] == "user_fact" and any(known[i]["role"] != "user" or
             content_identity(known[i]) != "user_statement" for i in lesson["source_ids"]):
            lesson["kind"] = "assistant_suggestion"
        lesson["text"] = redact(lesson["text"])
        lesson['domain']=str(lesson.get('domain','learning')).casefold()
    result["lessons"] = lessons
    return result


def audit_coverage(sessions, cards):
    covered = {c["project_id"] for c in cards}
    return {"missing_projects": sorted({s["project_id"] for s in sessions} - covered),
            "unresolved_sessions": [s["session_id"] for s in sessions if s["project_id"] not in covered]}


def safe_path(vault, name):
    if name not in (".knowledge_pipeline.json","05_Life/lessons.md","knowledge/personal_facts.md","knowledge/preferences.md","knowledge/history.md") and not re.fullmatch(r"02_Work/projects/[a-f0-9]{64}\.md", name):
        raise ValueError("unsupported pipeline path")
    path = vault / name
    if not path.resolve().is_relative_to(vault):
        raise ValueError("pipeline path escapes vault")
    return path


def recover(vault):
    from knowledge import _atomic_write
    journal = vault / ".knowledge_pending.json"
    if journal.exists():
        for name, content in json.loads(journal.read_text()).items():
            path = safe_path(vault, name)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write(path, base64.b64decode(content))
        journal.unlink()


def commit(vault, writes, run_id, index):
    from knowledge import _atomic_write
    originals = {}
    for name in writes:
        path = safe_path(vault, name)
        originals[name] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
    folder = vault / ".knowledge_backups" / run_id / f"{index:06d}"
    if not folder.resolve().is_relative_to(vault):
        raise ValueError("backup path escapes vault")
    manifest = {name: {"before": originals[name], "after": hashlib.sha256(content).hexdigest() if content is not None else None} for name, content in writes.items()}
    _atomic_write(folder / "pipeline-manifest.json", json.dumps(manifest).encode())
    _atomic_write(vault / ".knowledge_pending.json", json.dumps(originals).encode())
    try:
        for name, content in writes.items():
            if content is None:
                safe_path(vault, name).unlink(missing_ok=True)
            else:
                _atomic_write(safe_path(vault, name), content)
    except BaseException:
        recover(vault)
        _atomic_write(folder / "rolled-back", b"1")
        raise
    (vault / ".knowledge_pending.json").unlink()


def restore_pipeline_backup(vault, run_id):
    from knowledge import _locked, _atomic_write
    vault = Path(vault).resolve()
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}", run_id):
        raise ValueError("invalid run id")
    with _locked(vault):
        recover(vault)
        folder = vault / ".knowledge_backups" / run_id
        if not folder.resolve().is_relative_to(vault) or (folder / "restored").exists():
            raise ValueError("backup unavailable")
        simulated = {}
        manifests = sorted(folder.glob("*/pipeline-manifest.json"), reverse=True)
        if not manifests:
            raise ValueError("backup not found")
        for manifest in manifests:
            if (manifest.parent / "rolled-back").exists():
                continue
            for name, entry in json.loads(manifest.read_text()).items():
                path = safe_path(vault, name)
                content = simulated.get(name, path.read_bytes() if path.exists() else None)
                if (hashlib.sha256(content).hexdigest() if content is not None else None) != entry["after"]:
                    raise ValueError("file changed after import: " + name)
                simulated[name] = base64.b64decode(entry["before"]) if entry["before"] is not None else None
        # Journal restoration too, so a crash cannot leave half a restored cache.
        before = {n: base64.b64encode(safe_path(vault, n).read_bytes()).decode() if safe_path(vault,n).exists() else None for n in simulated}
        _atomic_write(vault / ".knowledge_pending.json", json.dumps(before).encode())
        for name, content in simulated.items():
            if content is None:
                safe_path(vault, name).unlink(missing_ok=True)
            else:
                _atomic_write(safe_path(vault, name), content)
        (vault / ".knowledge_pending.json").unlink()
        _atomic_write(folder / "restored", b"1")


def render_card(card):
    lines = ["# " + card["title"], "", "[ai-inference] Project summary",
             "Project: " + card["project_id"], "Updated: " + card["updated_at"],
             "Status: " + card["status"], "Verified: " + str(card["verified"]), "", card["intent"]]
    for field in ("blockers", "next_steps", "decisions"):
        lines.extend(["", "## " + field, *["- " + v for v in card[field]]])
    lines.extend(["", "Sources stored in .knowledge_pipeline.json: " + str(len(card["source_ids"])),
                  "Source: " + ", ".join(card["source_ids"][:8]), ""])
    return "\n".join(lines).encode()


def _project_unmanaged(vault, identity, previous=None):
    path=safe_path(vault,'02_Work/projects/'+digest(identity)+'.md')
    if not path.exists():return ''
    text=path.read_text(encoding='utf-8')
    start='<!-- selfos-managed-project-card -->'
    end='<!-- /selfos-managed-project-card -->'
    if start in text and end in text:
        return re.sub(re.escape(start)+r'.*?'+re.escape(end),'',text,flags=re.S)
    if previous is not None:
        generated=render_card(previous).decode('utf-8')
        if text.startswith(generated):return text[len(generated):]
    # Unrecognized legacy edits are retained intact, never guessed away.
    return text


def render_project_document(vault, card, previous=None):
    outside=_project_unmanaged(vault,card['project_id'],previous).rstrip()
    return (outside+('\n\n' if outside else '')+'<!-- selfos-managed-project-card -->\n'+
            render_card(card).decode('utf-8')+'<!-- /selfos-managed-project-card -->\n').encode('utf-8')


def _upgrade_cached_history(vault,state,domains,run_id,cancel,progress):
    if cancel():return 0
    from knowledge_history import rebuild_cached_state_history
    from knowledge_policy import record_writes
    count=rebuild_cached_state_history(state,domains)
    if not count or cancel():return 0
    history_writes=record_writes(vault,state)
    commit(vault,{'.knowledge_pipeline.json':json.dumps(state,ensure_ascii=False,indent=2).encode(),
                  'knowledge/history.md':history_writes['knowledge/history.md']},run_id,0)
    progress(f'Rebuilt cached state history for {count} projects; no model calls; backup {run_id}')
    return count


def consolidate_sessions(vault, sessions, summarize, max_workers=3, max_attempts=2,
                         cancel=lambda: False, progress=lambda _: None, settings=None, cached_summaries=None):
    from knowledge import _locked, _record_model_error
    from knowledge_policy import load_settings,validate_settings,limits,merge_records,record_writes
    settings=validate_settings(settings) if settings is not None else load_settings(vault)
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= 8:
        raise ValueError("max_workers must be 1..8")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be 1..5")
    vault = Path(vault).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    calls, completed, failed = 0, 0, []
    counter = threading.Lock()
    def worker(item, index):
        nonlocal calls
        token=(digest([item['project_id'],item['session_id'],item.get('part',0)]),item['fingerprint'])
        if cached_summaries and token in cached_summaries:
            try:
                cached=validate_summary(cached_summaries[token],item)
                cached.pop('_additional_api_calls',None)
                progress(f'Reused saved summary for session {index}; no model call')
                return cached,None
            except ValueError:
                pass  # Never reuse a checkpoint that fails current source validation.
        feedback = ""
        for attempt in range(1, max_attempts + 1):
            if cancel():
                return None, None
            with counter:
                calls += 1
            response = None
            try:
                response = summarize({**item, "repair_feedback": feedback,'policy':settings})
                with counter:
                    calls += response.get('_additional_api_calls',0) if isinstance(response,dict) else 0
                return validate_summary(response, item), None
            except Exception as error:
                with counter:
                    calls += getattr(error,'additional_api_calls',0)
                feedback = redact(str(error))[:1200]
                progress(f"Session {index}, attempt {attempt}/{max_attempts}: {feedback}")
                try:
                    _record_model_error(vault, run_id, index, attempt, item["messages"], response, error)
                except Exception:
                    pass
                if attempt < max_attempts and isinstance(error, (TimeoutError, OSError)):
                    # Interruptible bounded exponential backoff, including API quota errors.
                    seconds = min(8, 2 ** (attempt - 1))
                    if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                        break
                    for _ in range(seconds * 10):
                        if cancel():
                            return None, None
                        threading.Event().wait(0.1)
        return None, feedback
    with _locked(vault):
        recover(vault)
        state_path = safe_path(vault, ".knowledge_pipeline.json")
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"cache": {}, "cards": {}, "lessons": [], "sources": {}}
        state.setdefault("summaries", {})
        state['policy']=settings
        state.setdefault('retention_audit',[])
        history_upgraded=_upgrade_cached_history(vault,state,settings['domains'],run_id,cancel,progress)
        pending = []
        seen = set()
        for s in sessions:
            key = digest([s["project_id"], s["session_id"], s.get("part", 0)])
            token = (key, s["fingerprint"])
            if state["cache"].get(key) != s["fingerprint"] and token not in seen:
                pending.append((key, s))
                seen.add(token)
        progress(f"Knowledge: {len(sessions)} compact session parts, {len(pending)} pending; workers {max_workers}")
        iterator = iter(enumerate(pending, 1))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            active = {}
            def fill():
                while len(active) < max_workers and not cancel():
                    try:
                        index, (key, item) = next(iterator)
                    except StopIteration:
                        break
                    progress(f"Organizing session {index}/{len(pending)} ...")
                    active[executor.submit(worker, item, index)] = (index, key, item)
            fill()
            while active:
                done, _ = wait(active, timeout=0.2, return_when=FIRST_COMPLETED)
                for future in done:
                    index, key, item = active.pop(future)
                    candidate, error = future.result()
                    if error:
                        failed.append(item["session_id"])
                        continue
                    if candidate is None:
                        continue
                    if candidate.get('project') and candidate['project']['domain'] not in settings['domains']:
                        state['retention_audit'].append({'category':'project','source_ids':candidate['project']['source_ids'],'reason':'outside_selected_domains'})
                        candidate['project']=None
                    retained_lessons=[]
                    for lesson in candidate['lessons']:
                        if lesson['domain'] in settings['domains']:
                            retained_lessons.append(lesson)
                        else:
                            state['retention_audit'].append({'category':'lesson','source_ids':lesson['source_ids'],'reason':'outside_selected_domains'})
                    candidate['lessons']=retained_lessons
                    state['retention_audit'].extend(candidate.get('_retention_review',[]))
                    card = None
                    if candidate["project"] is not None:
                        previous_card=state["cards"].get(item["project_id"])
                        card = merge_project_card(previous_card, candidate["project"],limits(settings)['decisions'])
                        state["cards"][item["project_id"]] = card
                    for lesson in candidate["lessons"]:
                        if "lesson_history" in state and lesson not in state["lesson_history"]:
                            state["lesson_history"].append(copy.deepcopy(lesson))
                        existing = next((l for l in state["lessons"] if l["text"].casefold() == lesson["text"].casefold()
                                         and l["kind"] == lesson["kind"]
                                         and l.get('domain','work') == lesson.get('domain','work')), None)
                        if existing:
                            existing["source_ids"] = unique(existing["source_ids"] + lesson["source_ids"])
                        else:
                            state["lessons"].append(lesson)
                    state["cache"][key] = item["fingerprint"]
                    state["summaries"][key] = candidate
                    for category in ('personal_facts','preferences','history'):
                        merge_records(state,category,candidate.get(category,[]),settings)
                    for m in item["messages"]:
                        state["sources"][m["id"]] = {k: m.get(k, "") for k in ("path", "timestamp", "role", "source", "project_id", "session_id", "provenance")}
                    writes = {".knowledge_pipeline.json": json.dumps(state, ensure_ascii=False, indent=2).encode()}
                    if card is not None:
                        writes["02_Work/projects/" + digest(item["project_id"]) + ".md"] = render_project_document(vault,card,previous_card)
                    if candidate["lessons"]:
                        path = safe_path(vault, "05_Life/lessons.md")
                        old = path.read_text(encoding="utf-8") if path.exists() else "# Reusable lessons\n"
                        # Append only new sourced records; preserve unrelated existing text.
                        for lesson in candidate["lessons"]:
                            tag = "[" + lesson["kind"] + "] " + lesson["text"]
                            if tag not in old:
                                old += "\n- " + tag + "\n  Source: " + ", ".join(lesson["source_ids"]) + "\n"
                        writes["05_Life/lessons.md"] = old.encode()
                    writes.update(record_writes(vault,state))
                    commit(vault, writes, run_id, completed + 1)
                    completed += 1
                    progress(f"Saved session {index}/{len(pending)}; backup {run_id}")
                fill()
        coverage = audit_coverage(sessions, list(state["cards"].values()))
    return {"completed_sessions": completed, "failed_sessions": unique(failed), "model_calls": calls,
            "cancelled": bool(cancel()), "run_id": run_id if completed or history_upgraded else None,
            'history_upgraded':history_upgraded, **coverage}


def refine_projects(vault, refine, cancel=lambda: False, progress=lambda _: None):
    """Semantic synthesis of project history; never let synthesis alter observed current status."""
    from knowledge import _locked, _record_model_error, ResponseFormatError
    from knowledge_policy import limits,DEFAULT_SETTINGS
    vault = Path(vault).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    model_calls=0
    with _locked(vault):
        recover(vault)
        state_path = safe_path(vault, ".knowledge_pipeline.json")
        if not state_path.exists():
            return {"projects": 0, "run_id": None}
        state = json.loads(state_path.read_text(encoding="utf-8"))
        history_upgraded=_upgrade_cached_history(vault,state,state.get('policy',DEFAULT_SETTINGS)['domains'],run_id,cancel,progress)
        state.setdefault("lesson_history", copy.deepcopy(state["lessons"]))
        state.setdefault("refined", {})
        completed = 0
        for project_id, current in list(state["cards"].items()):
            if cancel():
                break
            lessons = [l for l in state["lesson_history"] if any(
                state["sources"].get(i, {}).get("project_id") == project_id for i in l["source_ids"])]
            source_ids = unique(current["source_ids"] + [i for l in lessons for i in l["source_ids"]])
            payload = {"project": copy.deepcopy(current), "lessons": copy.deepcopy(lessons),
                       "sources": {i: state["sources"][i] for i in source_ids}}
            payload['policy']=state.get('policy',DEFAULT_SETTINGS)
            payload["intent_history"] = [{"title": c["project"]["title"], "intent": c["project"]["intent"]}
                for c in state.get("summaries",{}).values() if c.get("project") and c["project"]["project_id"] == project_id]
            fingerprint = digest({'synthesis_version':SYNTHESIS_VERSION,"history":current.get("decision_history",current["decisions"]),
                "state": {k:current.get(k) for k in ("status","blockers","next_steps","updated_at")},
                "lessons": lessons, "sources": source_ids, "intent_history":payload["intent_history"], 'policy':payload['policy']})
            if state["refined"].get(project_id) == fingerprint:
                continue
            progress("Refining project: " + current["title"])
            item = {"project_id": project_id, "session_id": "project-refinement", "messages": [
                {"id": i, "text": "", **state["sources"][i]} for i in source_ids]}
            for attempt in range(3):
                if cancel():
                    return {"projects": completed, "run_id":run_id if completed else None,'model_calls':model_calls}
                response=None
                try:
                    model_calls+=1
                    response=refine(payload)
                    model_calls+=response.get('_additional_api_calls',0) if isinstance(response,dict) else 0
                    validated = validate_summary(response, item,lesson_limit=None)
                    observations=validate_summary({'project':response.get('project'),
                        'lessons':response.get('observations',[])},item,lesson_limit=None)['lessons']
                    break
                except Exception as error:
                    model_calls+=getattr(error,'additional_api_calls',0)
                    if cancel():
                        return {'projects':completed,'run_id':run_id if completed else None,'model_calls':model_calls}
                    diagnostic=_record_model_error(vault,run_id,completed+1,attempt+1,item['messages'],response,error)
                    progress(f'Diagnostic: vault/{diagnostic.as_posix()}')
                    if attempt == 2:
                        raise
                    payload["repair_feedback"] = redact(str(error))[:1200]
                    progress(f"Synthesis retry {attempt+1}/3: {payload['repair_feedback']}")
            if validated["project"] is None or len(validated["project"]["decisions"]) > limits(payload['policy'])['decisions']:
                raise ValueError("Refinement exceeds the configured current-view detail budget")
            for index,error in enumerate(validated.get('_lesson_review_errors',[]),1):
                diagnostic=_record_model_error(vault,run_id+f'-review-{completed+1}',index,error['attempt'],
                    item['messages'],None,ResponseFormatError(error['error'],error['raw_response']))
                state.setdefault('review_diagnostics',[]).append({'project_id':project_id,
                    'path':diagnostic.as_posix(),'batch_start':error['batch_start'],'attempt':error['attempt']})
                progress(f'Diagnostic: vault/{diagnostic.as_posix()}')
            domains=set(payload['policy']['domains'])
            def selected(records,category):
                kept=[]
                for record in records:
                    if record['domain'] in domains:kept.append(record)
                    else:state.setdefault('retention_audit',[]).append({'category':category,
                        'source_ids':record['source_ids'],'reason':'outside_selected_domains'})
                return kept
            validated['lessons']=selected(validated['lessons'],'lesson')
            observations=selected(observations,'project_observation')
            updated = {**current, **{k: validated["project"][k] for k in ("title", "intent", "decisions")}}
            updated["decision_history"] = current.get("decision_history", current["decisions"])
            state["cards"][project_id] = updated
            unrelated_lessons=[]
            for lesson in state['lessons']:
                remaining=[identity for identity in lesson['source_ids']
                           if state['sources'].get(identity,{}).get('project_id')!=project_id]
                if remaining:unrelated_lessons.append({**copy.deepcopy(lesson),'source_ids':remaining})
            state['lessons']=unrelated_lessons
            state["lessons"].extend(validated["lessons"])
            state.setdefault('retention_audit',[]).extend(validated.get('_lesson_review',[]))
            state['retention_audit'].extend({**entry,'stage':'cross_batch_method_merge'}
                for entry in validated.get('_lesson_merges',[]))
            state['retention_audit'].extend({**entry,'stage':'method_support_review'}
                for entry in validated.get('_method_support_review',[]))
            state['retention_audit'].extend({**entry,'stage':'project_observation_merge'}
                for entry in validated.get('_observation_merges',[]))
            previous_observations=[r for r in state.get('project_observations',[]) if r['project_id']==project_id]
            state.setdefault('project_observation_history',[])
            for record in previous_observations:
                if record not in state['project_observation_history']:state['project_observation_history'].append(copy.deepcopy(record))
            state['project_observations']=[r for r in state.get('project_observations',[]) if r['project_id']!=project_id]+[
                {**record,'project_id':project_id,'project_title':updated['title'],'kind':'inference','verified':False,
                 'original_category':'projects','source_scope':'summary_context',
                 'observed_at':max(state['sources'][identity].get('timestamp','') for identity in record['source_ids'])}
                for record in observations]
            state["quality_version"] = 2
            state["refined"][project_id] = fingerprint
            text = "# Reusable lessons\n\n<!-- selfos-managed-lessons -->\n" + "\n".join(
                "- [" + l["kind"] + "] " + l["text"] + "\n  Source: " + ", ".join(l["source_ids"])
                for l in state["lessons"]) + "\n<!-- /selfos-managed-lessons -->\n"
            lesson_path = safe_path(vault, "05_Life/lessons.md")
            if lesson_path.exists():
                old = lesson_path.read_text(encoding="utf-8")
                if "<!-- selfos-managed-lessons -->" in old:
                    outside = re.sub(r"<!-- selfos-managed-lessons -->.*?<!-- /selfos-managed-lessons -->", "", old, flags=re.S)
                    text = outside.rstrip() + "\n\n" + text.split("\n\n", 1)[1]
                else:
                    for lesson in state["lesson_history"]:
                        old = re.sub(r"\n- \[" + re.escape(lesson["kind"]) + r"\] " + re.escape(lesson["text"]) +
                                     r"\n  Source: [^\n]*\n?", "\n", old)
                    text = old.rstrip() + "\n\n" + text.split("\n\n",1)[1]
            from knowledge_policy import record_writes
            commit(vault, {**record_writes(vault,state),".knowledge_pipeline.json": json.dumps(state, ensure_ascii=False, indent=2).encode(),
                           "02_Work/projects/" + digest(project_id) + ".md": render_project_document(vault,updated,current),
                           "05_Life/lessons.md": text.encode()}, run_id, completed + 1)
            completed += 1
        return {"projects": completed, "run_id": run_id if completed or history_upgraded else None,
                'model_calls':model_calls,'history_upgraded':history_upgraded}


def install_rebuilt(vault, scratch, expected_hash=None, run_id=None, expected_policy_hash=None):
    from knowledge import _locked
    vault, scratch = Path(vault).resolve(), Path(scratch).resolve()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    with _locked(vault):
        recover(vault)
        state_path = safe_path(vault, ".knowledge_pipeline.json")
        actual_hash = hashlib.sha256(state_path.read_bytes()).hexdigest() if state_path.exists() else 'absent'
        if expected_hash and actual_hash != expected_hash:
            raise ValueError("Canonical import changed during rebuild; replacement aborted")
        if expected_policy_hash:
            from knowledge_policy import load_settings, policy_hash
            if policy_hash(load_settings(vault)) != expected_policy_hash:
                raise ValueError('Settings changed during rebuild; replacement aborted')
        old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"cards":{}}
        new = json.loads(safe_path(scratch, ".knowledge_pipeline.json").read_text(encoding="utf-8"))
        if new.get("quality_version") != 2:
            raise ValueError("Rebuild requires completed semantic refinement")
        writes = {".knowledge_pipeline.json":safe_path(scratch, ".knowledge_pipeline.json").read_bytes()}
        for identity in old["cards"]:
            if identity not in new["cards"]:
                notes=_project_unmanaged(vault,identity,old['cards'][identity])
                writes["02_Work/projects/" + digest(identity) + ".md"] = notes.encode('utf-8') if notes.strip() else None
        for identity, card in new["cards"].items():
            from knowledge_policy import limits
            if len(card["decisions"]) > limits(new.get('policy'))['decisions']:
                raise ValueError("Rebuilt card is not compact")
            writes["02_Work/projects/" + digest(identity) + ".md"] = render_project_document(vault,card,old['cards'].get(identity))
        lessons = safe_path(scratch, "05_Life/lessons.md")
        if lessons.exists():
            replacement = lessons.read_text(encoding="utf-8")
            current = safe_path(vault,"05_Life/lessons.md")
            if current.exists():
                outside = current.read_text(encoding="utf-8")
                if "<!-- selfos-managed-lessons -->" in outside:
                    outside = re.sub(r"<!-- selfos-managed-lessons -->.*?<!-- /selfos-managed-lessons -->","",outside,flags=re.S)
                else:
                    for lesson in old.get("lessons",[]):
                        outside = re.sub(r"\n- \["+re.escape(lesson["kind"])+r"\] "+re.escape(lesson["text"])+
                                         r"\n  Source: [^\n]*\n?","\n",outside)
                if "<!-- selfos-managed-lessons -->" in replacement:
                    replacement = outside.rstrip()+"\n\n<!-- selfos-managed-lessons -->"+replacement.split("<!-- selfos-managed-lessons -->",1)[1]
                else:
                    replacement = outside.rstrip()+"\n\n"+replacement
            writes["05_Life/lessons.md"] = replacement.encode()
        from knowledge_policy import FILES
        for name in FILES.values():
            source=safe_path(scratch,name)
            if source.exists():
                target=safe_path(vault,name)
                text=source.read_text(encoding='utf-8')
                if target.exists():
                    marker=re.search(r'<!-- selfos-managed-([^ >]+) -->',text)
                    if marker:
                        tag=marker.group(1)
                        outside=re.sub(r'<!-- selfos-managed-'+re.escape(tag)+r' -->.*?<!-- /selfos-managed-'+re.escape(tag)+r' -->','',target.read_text(encoding='utf-8'),flags=re.S)
                        text=outside.rstrip()+'\n\n'+text[text.index('<!-- selfos-managed-'):]
                writes[name]=text.encode()
        commit(vault, writes, run_id, 1)
    return run_id


def register_project_aliases(vault, aliases):
    """Persist explicit reviewed identity aliases, retaining every original source path."""
    from knowledge import _locked
    vault = Path(vault).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    with _locked(vault):
        recover(vault)
        state = json.loads(safe_path(vault, ".knowledge_pipeline.json").read_text(encoding="utf-8"))
        for origin, target in aliases.items():
            if not isinstance(origin,str) or not isinstance(target,str) or origin == target or target in aliases:
                raise ValueError("Aliases must point directly to distinct canonical projects")
        state.setdefault("project_aliases", {}).update(aliases)
        writes = {}
        for origin, target in aliases.items():
            if origin not in state["cards"]:
                continue
            update = state["cards"].pop(origin)
            update["project_id"] = target
            state["cards"][target] = merge_project_card(state["cards"].get(target), update)
            writes["02_Work/projects/"+digest(origin)+".md"] = None
            writes["02_Work/projects/"+digest(target)+".md"] = render_card(state["cards"][target])
        for source in state["sources"].values():
            if source.get("project_id") in aliases:
                source.setdefault("original_project_id",source["project_id"])
                source["project_id"] = aliases[source["project_id"]]
        for candidate in state.get("summaries",{}).values():
            if candidate.get("project") and candidate["project"]["project_id"] in aliases:
                candidate["project"]["project_id"] = aliases[candidate["project"]["project_id"]]
        for origin,target in aliases.items():
            state.setdefault("refined",{}).pop(origin,None)
            state["refined"].pop(target,None)
        writes[".knowledge_pipeline.json"] = json.dumps(state,ensure_ascii=False,indent=2).encode()
        commit(vault,writes,run_id,1)
    return run_id
