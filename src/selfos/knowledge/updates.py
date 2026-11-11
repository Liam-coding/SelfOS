"""knowledge / updates responsibilities."""
from selfos.knowledge.contracts import TARGETS
from selfos.sources.text import redact

def _validate_updates(updates, batch):
    if not isinstance(updates, list):
        raise ValueError('AI response must be a JSON array')
    sources = {m['id']: m for m in batch}
    valid = []
    kind_aliases = {'fact': 'user_fact', 'user': 'user_fact',
                    'suggestion': 'assistant_suggestion', 'assistant': 'assistant_suggestion',
                    'ai_inference': 'inference', 'ai-inference': 'inference', 'inferred': 'inference'}
    for update_index, update in enumerate(updates):
        location = f'updates[{update_index}]'
        if not isinstance(update, dict) or update.get('target') not in TARGETS:
            raise ValueError(f'{location}.target: unsupported vault target; use an allowed module')
        facts = update.get('facts')
        if not isinstance(facts, list):
            raise ValueError(f'{location}.facts: expected an array of knowledge facts')
        for fact_index, fact in enumerate(facts):
            field = f'{location}.facts[{fact_index}]'
            if not isinstance(fact, dict):
                raise ValueError(f'{field}: expected an object')
            text, ids, kind = fact.get('text'), fact.get('source_ids'), fact.get('kind')
            issues = []
            if not isinstance(text, str) or not text.strip():
                issues.append(f'{field}.text: expected a non-empty string; omit an empty fact')
            else:
                text = text.strip()
                if len(text) > 4000:
                    issues.append(f'{field}.text: {len(text)} characters exceeds 4000; rewrite concisely without losing meaning')
            if isinstance(ids, str):
                ids = [ids]
            if not isinstance(ids, list) or not ids or any(not isinstance(s, str) or not s.strip() for s in ids):
                issues.append(f'{field}.source_ids: expected a non-empty list of exact source IDs')
            else:
                ids = [s.strip() for s in ids]
                if any(s not in sources for s in ids):
                    issues.append(f'{field}.source_ids: contains an ID outside this batch; use only the supplied source IDs')
            if kind is None:
                kind = 'inference'
            if not isinstance(kind, str):
                issues.append(f'{field}.kind: expected user_fact, assistant_suggestion or inference')
            else:
                kind = kind.strip().casefold()
                kind = kind_aliases.get(kind, kind)
                if kind not in ('user_fact', 'assistant_suggestion', 'inference'):
                    issues.append(f'{field}.kind: unsupported category; use user_fact, assistant_suggestion or inference')
            if issues:
                raise ValueError('; '.join(issues))
            if kind == 'user_fact' and any(sources[s]['role'] != 'user' for s in ids):
                kind = 'assistant_suggestion'
            valid.append((update['target'], redact(text).strip(), sorted(set(ids)), kind))
    return valid
