"""Build real SelfOS dashboards from fictional, reusable bilingual data."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def build(fixture, locale, output):
    from selfos.web.rendering.dashboard import generate_dashboard
    from selfos.app.library import list_knowledge, knowledge_detail, knowledge_timeline
    from selfos.knowledge.identity import digest
    from selfos.storage.records import record_writes
    from selfos.knowledge.records import validate_record
    vault = output / locale / 'vault'
    vault.mkdir(parents=True, exist_ok=True)
    state = {'cards': {}, 'sources': {}, 'lessons': [], 'personal_facts': [], 'preferences': [], 'history': []}
    texts = {}
    def source(key, text, index):
        identity = digest(['selfos-synthetic-demo', locale, key, text])
        message = {'id': identity, 'role': 'user', 'text': text, 'source': 'claude' if index % 2 else 'codex',
                   'path': 'synthetic-' + key + '.jsonl', 'timestamp': '2026-11-12T08:%02d:00Z' % index,
                   'project_id': 'demo-' + key, 'project': key, 'session_id': 'demo-' + key}
        state['sources'][identity] = message
        texts[identity] = text
        return message
    for index, project in enumerate(fixture['projects']):
        title, intent, decision, next_step = project[locale]
        message = source(project['key'], '\n'.join([title, intent, decision, next_step]), index)
        state['cards'][message['project_id']] = {'project_id': message['project_id'], 'title': title,
            'intent': intent, 'domain': project['domain'], 'status': 'in_progress', 'verified': False,
            'decisions': [decision], 'next_steps': [next_step], 'blockers': [], 'source_ids': [message['id']],
            'updated_at': message['timestamp']}
    for index, record in enumerate(fixture['records'], 5):
        value, text = record[locale]
        message = source(record['project'], text, index)
        raw = {'key': record['key'], 'value': value, 'text': text,
               'domain': next(p['domain'] for p in fixture['projects'] if p['key'] == record['project']),
               'kind': 'inference' if record['category'] == 'lessons' else 'user_fact',
               'temporal': 'historical' if record['category'] == 'history' else 'current',
               'source_ids': [message['id']], 'evidence': text, 'observed_at': message['timestamp']}
        checked = validate_record(raw, {'project_id': message['project_id'], 'messages': [message]})
        state[record['category']].append(checked)
    (vault / '.knowledge_pipeline.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    (vault.parent / 'synthetic-conversations.json').write_text(json.dumps(list(state['sources'].values()), ensure_ascii=False, indent=2), encoding='utf-8')
    (vault / 'PROFILE.md').write_text('# Fictional demonstration profile\n- Preferred name: ' + ('Demo' if locale == 'en' else '\u793a\u4f8b\u7528\u6237') + '\n', encoding='utf-8')
    scores = fixture['scores']
    (vault / 'SCORES.md').write_text('\n'.join('- 2026-11-%02d | ' % day + ' | '.join('%s: %s' % (key, max(3, score - ((12-day)//5))) for key, score in scores.items()) for day in range(1, 13)), encoding='utf-8')
    for name, content in record_writes(vault, state).items():
        path = vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    page = generate_dashboard(vault, scores=scores).read_text(encoding='utf-8')
    listing = list_knowledge(vault, limit=200)
    details = {row['id']: knowledge_detail(vault, row['id']) for row in listing['items']}
    timelines = {row['id']: knowledge_timeline(vault, row['id'], limit=200) for row in listing['items'] if row['category'] == 'projects'}
    payload = {'listing': listing, 'details': details, 'timelines': timelines, 'texts': texts, 'counts': listing['counts']}
    encoded = json.dumps(payload, ensure_ascii=True).replace('<', '\u003c').replace('>', '\u003e').replace('&', '\u0026')
    adapter = (ROOT / 'demo-adapter.js').read_text(encoding='utf-8').replace('__DEMO_DATA__', encoded).replace('__DEMO_LOCALE__', 'zh-CN' if locale == 'zh' else 'en')
    page = page.replace('<head>', '<head><script>' + adapter + '</script>', 1)
    label = 'Demo data · completely fictional' if locale == 'en' else '演示数据 · 全部为虚构内容'
    banner = '<div style="display:flex;justify-content:space-between;gap:16px;align-items:center;max-width:1440px;margin:0 auto 18px;color:#64748b;font:12px system-ui"><span>' + label + '</span><a style="color:#2563eb;text-decoration:none" href="https://github.com/Liam-coding/SelfOS">github.com/Liam-coding/SelfOS</a></div>'
    page = page.replace('<body>', '<body>' + banner, 1)
    assert sum(listing['counts'].values()) == len(fixture['projects']) + len(fixture['records'])
    for detail in details.values():
        assert detail['source_count'] > 0 and not detail['item']['missing_source_count']
    destination = output / ('selfos-' + locale + '.html')
    destination.write_text(page, encoding='utf-8')
    return destination, listing['counts']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT.parent.parent)
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve() / 'src'))
    import selfos
    assert Path(selfos.__file__).resolve().is_relative_to(args.repo.resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    fixture = json.loads((ROOT / 'fixture.json').read_text(encoding='utf-8'))
    assert fixture['synthetic'] is True
    for locale in ('zh', 'en'):
        page, counts = build(fixture, locale, args.output)
        print(page.name, counts)
