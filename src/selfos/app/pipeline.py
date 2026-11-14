"""app / pipeline responsibilities."""
import copy
import hashlib
import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import threading
import uuid
from urllib.error import HTTPError
from selfos.storage.pipeline import commit
from selfos.knowledge.projects import audit_coverage
from selfos.knowledge.identity import digest
from selfos.knowledge.projects import merge_project_card
from selfos.storage.pipeline import recover
from selfos.sources.text import redact
from selfos.storage.documents import render_project_document
from selfos.storage.pipeline import safe_path
from selfos.knowledge.identity import unique
from selfos.knowledge.projects import validate_summary
from selfos.storage.documents import _project_unmanaged
from selfos.storage.documents import render_card

SYNTHESIS_VERSION = 12


def _upgrade_cached_history(vault,state,domains,run_id,cancel,progress):
    if cancel():return 0
    from selfos.knowledge.history import rebuild_cached_state_history
    from selfos.storage.records import record_writes
    count=rebuild_cached_state_history(state,domains)
    if not count or cancel():return 0
    history_writes=record_writes(vault,state)
    commit(vault,{'.knowledge_pipeline.json':json.dumps(state,ensure_ascii=False,indent=2).encode(),
                  'knowledge/history.md':history_writes['knowledge/history.md']},run_id,0)
    progress(f'Rebuilt cached state history for {count} projects; no model calls; backup {run_id}')
    return count


def consolidate_sessions(vault, sessions, summarize, max_workers=3, max_attempts=2,
                         cancel=lambda: False, progress=lambda _: None, settings=None, cached_summaries=None,
                         upgrade_history=True):
    from selfos.storage.files import _locked
    from selfos.app.diagnostics import _record_model_error
    from selfos.storage.settings import load_settings
    from selfos.knowledge.settings import validate_settings, limits
    from selfos.knowledge.records import merge_records
    from selfos.storage.records import record_writes
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
        history_upgraded=_upgrade_cached_history(vault,state,settings['domains'],run_id,cancel,progress) if upgrade_history else 0
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
                    state.setdefault('quality_sessions', {})[key] = {
                        'run_id': run_id,
                        'source_ids': [message['id'] for message in item['messages']],
                        'categories': {category: len(candidate.get(category, []))
                            for category in ('personal_facts', 'preferences', 'history', 'lessons')}}
                    for category in ('personal_facts','preferences','history'):
                        merge_records(state,category,candidate.get(category,[]),settings)
                    for m in item["messages"]:
                        from selfos.sources.documents import source_metadata
                        state["sources"][m["id"]] = source_metadata(m, state["sources"].get(m["id"]))
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


def refine_projects(vault, refine, cancel=lambda: False, progress=lambda _: None,
                    project_ids=None, context_filter=None, upgrade_history=True):
    """Semantic synthesis of project history; never let synthesis alter observed current status."""
    from selfos.storage.files import _locked
    from selfos.app.diagnostics import _record_model_error
    from selfos.knowledge.contracts import ResponseFormatError
    from selfos.knowledge.settings import limits, DEFAULT_SETTINGS
    vault = Path(vault).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    model_calls=0
    with _locked(vault):
        recover(vault)
        state_path = safe_path(vault, ".knowledge_pipeline.json")
        if not state_path.exists():
            return {"projects": 0, "run_id": None}
        state = json.loads(state_path.read_text(encoding="utf-8"))
        history_upgraded=_upgrade_cached_history(vault,state,state.get('policy',DEFAULT_SETTINGS)['domains'],run_id,cancel,progress) if upgrade_history else 0
        state.setdefault("lesson_history", copy.deepcopy(state["lessons"]))
        state.setdefault("refined", {})
        completed = 0
        for project_id, current in list(state["cards"].items()):
            if project_ids is not None and project_id not in project_ids:
                continue
            if cancel():
                break
            lessons = [l for l in state["lesson_history"] if any(
                state["sources"].get(i, {}).get("project_id") == project_id for i in l["source_ids"])]
            source_ids = unique(current["source_ids"] + [i for l in lessons for i in l["source_ids"]])
            payload = {"project": copy.deepcopy(current), "lessons": copy.deepcopy(lessons),
                       "sources": {i: state["sources"][i] for i in source_ids}}
            from selfos.storage.corrections import load_corrections
            ledger=load_corrections(vault)
            if any(action.get('active',True) for action in ledger['actions']):
                from selfos.knowledge.corrections import apply_corrections
                projection=apply_corrections(state,ledger)
                payload['user_corrections']={
                    'project':projection.get('cards',{}).get(project_id),
                    'lessons':[l for l in projection.get('lessons',[]) if any(
                        state['sources'].get(i,{}).get('project_id')==project_id for i in l.get('source_ids',[]))],
                    'notice':'User corrections are separate from original source evidence. Do not silently overwrite them.'}
            payload['policy']=state.get('policy',DEFAULT_SETTINGS)
            payload["intent_history"] = [{"title": c["project"]["title"], "intent": c["project"]["intent"]}
                for c in state.get("summaries",{}).values() if c.get("project") and c["project"]["project_id"] == project_id]
            if context_filter is not None:
                payload = context_filter(payload, state)
                if payload is None:
                    continue
                lessons = payload['lessons']
                source_ids = list(payload['sources'])
            fingerprint = digest({'synthesis_version':SYNTHESIS_VERSION,"history":current.get("decision_history",current["decisions"]),
                "state": {k:current.get(k) for k in ("status","blockers","next_steps","updated_at")},
                "lessons": lessons, "sources": source_ids, "intent_history":payload["intent_history"], 'policy':payload['policy']})
            if 'user_corrections' in payload:fingerprint=digest([fingerprint,payload['user_corrections']])
            if context_filter is not None:
                fingerprint = digest([fingerprint, payload])
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
                if context_filter is not None and not set(lesson['source_ids']).issubset(payload['sources']):
                    unrelated_lessons.append(copy.deepcopy(lesson))
                    continue
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
            state['project_observations']=[r for r in state.get('project_observations',[]) if r['project_id']!=project_id or
                (context_filter is not None and not set(r['source_ids']).issubset(payload['sources']))]+[
                {**record,'project_id':project_id,'project_title':updated['title'],'kind':'inference','verified':False,
                 'original_category':'projects','source_scope':'summary_context',
                 'observed_at':max(state['sources'][identity].get('timestamp','') for identity in record['source_ids'])}
                for record in observations]
            state["quality_version"] = 2
            state["refined"][project_id] = fingerprint
            # Save recovery evidence atomically with the successful refinement.
            # Extraction outcomes cannot establish synthesis/review success.
            state.setdefault('quality_refinements', {})[run_id + ':' + project_id] = {
                'run_id': run_id, 'review_run_id': run_id + f'-review-{completed+1}',
                'source_ids': list(source_ids), 'fingerprint': fingerprint}
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
            from selfos.storage.records import record_writes
            commit(vault, {**record_writes(vault,state),".knowledge_pipeline.json": json.dumps(state, ensure_ascii=False, indent=2).encode(),
                           "02_Work/projects/" + digest(project_id) + ".md": render_project_document(vault,updated,current),
                           "05_Life/lessons.md": text.encode()}, run_id, completed + 1)
            completed += 1
        return {"projects": completed, "run_id": run_id if completed or history_upgraded else None,
                'model_calls':model_calls,'history_upgraded':history_upgraded}


def install_rebuilt(vault, scratch, expected_hash=None, run_id=None, expected_policy_hash=None, selected_projects=None,
                    expected_privacy_hash=None):
    from selfos.storage.files import _locked
    from selfos.storage.settings import load_settings
    from selfos.sources.selection import policy_lock
    vault, scratch = Path(vault).resolve(), Path(scratch).resolve()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    with _locked(vault), policy_lock(vault):
        recover(vault)
        if expected_privacy_hash is not None:
            from selfos.app.privacy import selection_hash
            if selection_hash(vault) != expected_privacy_hash:
                raise ValueError('Privacy rules changed; restart the import')
        state_path = safe_path(vault, ".knowledge_pipeline.json")
        actual_hash = hashlib.sha256(state_path.read_bytes()).hexdigest() if state_path.exists() else 'absent'
        if expected_hash and actual_hash != expected_hash:
            raise ValueError("Canonical import changed during rebuild; replacement aborted")
        if expected_policy_hash:
            from selfos.storage.settings import load_settings
            from selfos.knowledge.settings import policy_hash
            if policy_hash(load_settings(vault)) != expected_policy_hash:
                raise ValueError('Settings changed during rebuild; replacement aborted')
        old = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"cards":{}}
        new = json.loads(safe_path(scratch, ".knowledge_pipeline.json").read_text(encoding="utf-8"))
        if selected_projects is None and new.get("quality_version") != 2:
            raise ValueError("Rebuild requires completed semantic refinement")
        writes = {".knowledge_pipeline.json":safe_path(scratch, ".knowledge_pipeline.json").read_bytes()}
        for identity in old["cards"]:
            if selected_projects is not None and identity not in selected_projects:
                if new['cards'].get(identity) != old['cards'][identity]:
                    raise ValueError("Sample changed an unrelated project")
                continue
            if identity not in new["cards"]:
                notes=_project_unmanaged(vault,identity,old['cards'][identity])
                writes["02_Work/projects/" + digest(identity) + ".md"] = notes.encode('utf-8') if notes.strip() else None
        for identity, card in new["cards"].items():
            if selected_projects is not None and identity not in selected_projects:
                continue
            from selfos.knowledge.settings import limits
            if len(card["decisions"]) > limits(load_settings(vault) if selected_projects is not None else new.get('policy'))['decisions']:
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
        from selfos.knowledge.settings import FILES
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
        from selfos.storage.corrections import load_corrections
        ledger=load_corrections(vault)
        if ledger['actions']:
            from selfos.storage.records import record_writes
            # Rebuild outputs can predate a user action. Project the latest local
            # ledger under this same lock without rewriting generated state.
            writes.update(record_writes(vault,new,corrections=ledger))
        if expected_privacy_hash is not None and selection_hash(vault) != expected_privacy_hash:
            raise ValueError('Privacy rules changed; restart the import')
        commit(vault, writes, run_id, 1)
    return run_id


def register_project_aliases(vault, aliases):
    """Persist explicit reviewed identity aliases, retaining every original source path."""
    from selfos.storage.files import _locked
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
            if source.get('source') == 'opencode':
                continue  # Immutable adapter identity is independent of application grouping.
            if source.get("project_id") in aliases:
                source.setdefault("original_project_id",source["project_id"])
                source["project_id"] = aliases[source["project_id"]]
        for candidate in state.get("summaries",{}).values():
            if candidate.get("project") and candidate["project"]["project_id"] in aliases:
                candidate["project"]["project_id"] = aliases[candidate["project"]["project_id"]]
        def migrate_scope(record):
            scope=record.get('scope')
            if isinstance(scope,dict) and scope.get('type')=='project' and scope.get('id') in aliases:
                scope['id']=aliases[scope['id']]
            elif record.get('scope_type')=='project' and isinstance(scope,str) and scope in aliases:
                record['scope']=aliases[scope]
        preferences=state.get('preferences',[])
        for record in preferences:migrate_scope(record)
        for record in state.get('personal_facts',[]):migrate_scope(record)
        for category in ('history','records_history'):
            for record in state.get(category,[]):
                if record.get('original_category') in ('preferences','personal_facts'):migrate_scope(record)
        for candidate in state.get('summaries',{}).values():
            for record in candidate.get('preferences',[]):migrate_scope(record)
            for record in candidate.get('personal_facts',[]):migrate_scope(record)
            for record in candidate.get('history',[]):
                if record.get('original_category') in ('preferences','personal_facts'):migrate_scope(record)
        # Aliased projects can now share a preference relation. Consolidate support locally.
        from selfos.knowledge.preferences import merge_preferences
        state['preferences']=[]
        state.setdefault('records_history',[])
        for record in preferences:merge_preferences(state,record)
        from selfos.knowledge.personal_facts import reconsolidate_facts
        reconsolidate_facts(state)
        from selfos.storage.records import record_writes
        writes.update(record_writes(vault,state))
        for origin,target in aliases.items():
            state.setdefault("refined",{}).pop(origin,None)
            state["refined"].pop(target,None)
        writes[".knowledge_pipeline.json"] = json.dumps(state,ensure_ascii=False,indent=2).encode()
        commit(vault,writes,run_id,1)
    return run_id
