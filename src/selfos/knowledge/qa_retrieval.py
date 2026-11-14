"""Deterministic bounded retrieval over the existing retained-record projection."""
import copy
import re

from selfos.knowledge.identity import digest
from selfos.knowledge.search import WEIGHTS

MAX_RECORDS = 8
MAX_TEXT_CHARS = 12000
MAX_RECORD_CHARS = 2000
MAX_REFERENCES = 24
ACTIVE_PROJECTS = {'active', 'in_progress', 'blocked', 'planning', 'paused', 'ongoing'}
STOP_WORDS = set('what why how when where which who am are is was were do does did i me my we our you your a an the to for of in on about regarding please tell explain know currently now working work previously before used choose chose chosen prefer prefers preferred preference preferences personal facts lessons experiences decision decisions'.split())
CHINESE_SCAFFOLD = ('我现在在做什么', '我正在做什么', '我在做什么', '你知道我的哪些信息', '关于我有哪些信息',
                    '为什么', '如何', '是什么', '有什么', '哪些', '我的偏好', '我的习惯', '我的经验', '个人事实',
                    '我的', '我们', '我', '现在', '以前', '之前', '曾经', '关于', '方面', '选择', '喜欢', '偏好', '的', '吗')


def question_terms(question):
    folded = question.casefold()
    terms = [word for word in re.findall(r'[a-z0-9_+-]+', folded) if word not in STOP_WORDS]
    chinese = folded
    for phrase in CHINESE_SCAFFOLD:
        chinese = chinese.replace(phrase, ' ')
    for chunk in re.findall(r'[\u4e00-\u9fff]+', chinese):
        if len(chunk) <= 2:
            terms.append(chunk)
        else:
            terms.extend(chunk[i:i+2] for i in range(len(chunk)-1))
            terms.append(chunk)
    return list(dict.fromkeys(terms))[:32]


def _intent(question):
    folded = ' '.join(question.casefold().split())
    historical = bool(re.search(r'\b(previously|before|past|historical|history|used to|why|decision|decisions)\b|以前|之前|曾经|历史|为什么|决策|决定|选择', folded))
    patterns = _overview_patterns()
    category = next((key for key, pattern in patterns.items() if re.search(pattern, folded)), None)
    return category, historical


def _overview_patterns():
    return {
        'projects': r'what am i working on|current projects|active projects|我现在在做什么|我正在做什么|我在做什么|当前项目',
        'preferences': r'my preferences|我的偏好|我的习惯',
        'personal_facts': r'what do you know about me|my personal facts|关于我有哪些信息|你知道我的哪些信息|个人事实',
        'lessons': r'my lessons|my reusable experience|what have i learned|我的经验|可复用经验',
    }


def _fields(row, detail):
    return {**{name: str(detail.get(name, '')) for name in ('title', 'summary', 'evidence')},
            **{name: ' '.join(str(value) for value in detail.get(name, [])) for name in ('decisions', 'blockers', 'next_steps')}}


def _score(fields, terms):
    # Weak domain/context labels alone do not support a specific personal answer.
    return sum(WEIGHTS.get(name, 1) * sum(term in text.casefold() for term in terms)
               for name, text in fields.items())


def _project(row, detail, sources, terms, remaining):
    clipped = {key: value for key, value in detail.items() if key not in ('decisions', 'blockers', 'next_steps')}
    for field in ('title', 'summary', 'evidence'):
        clipped[field] = str(detail.get(field, ''))[:{'title': 240, 'summary': 1200, 'evidence': 800}[field]]
    for field in ('decisions', 'blockers', 'next_steps'):
        values = [str(value) for value in detail.get(field, [])]
        values.sort(key=lambda value: sum(term in value.casefold() for term in terms), reverse=True)
        clipped[field] = [value[:500] for value in values[:4]]
    fields = _fields(row, clipped)
    fields = sorted(fields.items(), key=lambda pair: WEIGHTS.get(pair[0], 1) * sum(term in pair[1].casefold() for term in terms), reverse=True)
    text = '\n'.join(name + ': ' + value for name, value in fields if value)[:min(MAX_RECORD_CHARS, remaining)]
    supporting = set(detail.get('supporting_source_ids', []))
    ordered = sorted(sources, key=lambda source: (source.get('id') in supporting, source.get('timestamp', '')), reverse=True)
    picked = [{key: str(source.get(key, ''))[:512] for key in
               ('id', 'file', 'source', 'timestamp', 'role', 'provenance', 'session_id', 'timestamp_kind')}
              for source in ordered[:3]]
    return dict(record={**copy.deepcopy(row), 'title': clipped['title'], 'summary': clipped['summary']},
                detail=copy.deepcopy(clipped), text=text, sources=picked,
                source_count=len(sources), source_coverage='representative' if len(sources) > len(picked) else 'complete',
                historical=row['category'] == 'history', revision=digest(detail))


def retrieve_records(records, question, project=''):
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError('Question must contain 1..2000 characters')
    if not isinstance(project, str) or len(project) > 100:
        raise ValueError('Invalid question project scope')
    category, historical = _intent(question)
    lexical_question = ' '.join(question.casefold().split())
    if category:
        lexical_question = re.sub(_overview_patterns()[category], ' ', lexical_question)
    terms = question_terms(lexical_question)
    candidates = []
    for row, detail, sources, _ in records:
        if not sources or (row['category'] == 'history' and not historical):
            continue
        if project and not any(context['id'] == project for context in row.get('project_contexts', [])):
            continue
        if category and row['category'] != category and not (historical and row['category'] == 'history'):
            continue
        if category == 'projects' and row['category'] == 'projects' and row.get('status') not in ACTIVE_PROJECTS:
            continue
        score = _score(_fields(row, detail), terms)
        if not score and (terms or not (category or project)):
            continue
        candidates.append((score, row.get('date', ''), row['id'], row, detail, sources))
    candidates.sort(key=lambda item: item[:3], reverse=True)
    selected, remaining = [], MAX_TEXT_CHARS
    for _, _, _, row, detail, sources in candidates[:MAX_RECORDS]:
        if remaining <= 0:
            break
        projection = _project(row, detail, sources, terms, remaining)
        remaining -= len(projection['text'])
        selected.append(projection)
    return selected
