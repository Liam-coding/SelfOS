"""knowledge / projects responsibilities."""
import copy
import re
from selfos.knowledge.identity import unique
from selfos.knowledge.filtering import content_identity
from selfos.sources.text import redact

def clean_actions(items):
    return [item for item in items if not re.match(
        r"^\s*(?:Call|Invoke|调用|执行)\s*(?:ScheduleWakeup|request_user_input_async|SendMessage|GetHandoffStatus)\b",item,re.I)]


def merge_project_card(current, update, limit=8):
    from selfos.knowledge.history import collect_state_records
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
    from selfos.knowledge.records import validate_record
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
