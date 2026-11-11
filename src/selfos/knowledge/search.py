"""Deterministic search over redacted canonical fields, without model calls."""
from datetime import date

WEIGHTS = {'title': 8, 'summary': 5, 'decisions': 4, 'blockers': 3,
           'next_steps': 3, 'evidence': 3, 'project_context': 1, 'domain': 1}


def search_terms(query):
    if not isinstance(query, str) or len(query) > 500:
        raise ValueError('Search query is too long')
    terms = list(dict.fromkeys(query.strip().casefold().split()))
    if len(terms) > 20:
        raise ValueError('Use at most 20 search terms')
    return terms


def date_bound(value):
    if not isinstance(value, str):
        raise ValueError('Date filter must be YYYY-MM-DD')
    if not value:
        return ''
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise ValueError('Date filter must be YYYY-MM-DD') from None
    return value


def _ranges(text, terms):
    folded, positions = [], []
    for position, char in enumerate(text):
        value = char.casefold()
        folded.append(value)
        positions.extend([position] * len(value))
    folded = ''.join(folded)
    ranges = []
    for term in terms:
        start = folded.find(term)
        while start >= 0:
            end = start + len(term)
            ranges.append((positions[start], positions[end - 1] + 1))
            start = folded.find(term, end)
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def match_fields(fields, query, terms):
    folded = {name: text.casefold() for name, text in fields.items()}
    if any(not any(term in text for text in folded.values()) for term in terms):
        return None
    phrase = ' '.join(query.strip().casefold().split())
    scores = {}
    for name, text in folded.items():
        weight = WEIGHTS[name]
        scores[name] = weight * sum(term in text for term in terms)
        if phrase and phrase in text:
            scores[name] += weight * 20
            if text == phrase:
                scores[name] += weight * 50
    field = max(scores, key=scores.get) if terms else ('summary' if fields['summary'] else 'title')
    text = fields[field]
    ranges = _ranges(text, terms)
    start = max(0, (ranges[0][0] if ranges else 0) - 72)
    end = min(len(text), start + 260)
    prefix, suffix = ('…' if start else ''), ('…' if end < len(text) else '')
    return {'search_score': sum(scores.values()), 'match_field': field,
            'match_excerpt': prefix + text[start:end] + suffix,
            'match_ranges': [[max(left, start) - start + len(prefix), min(right, end) - start + len(prefix)]
                             for left, right in ranges if left < end and right > start]}
