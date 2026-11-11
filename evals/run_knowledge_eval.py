"""Repeatable synthetic-dialogue checks. Live API calls require an explicit --live flag."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def flatten_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        ignored = {'source_ids', 'project_id', 'updated_at', 'verified', 'kind'}
        return '\n'.join(flatten_text(item) for key, item in value.items() if key not in ignored)
    return ''


def grade_case(case, texts, *, source_valid=True):
    """Literal concept alternatives and forbidden claims; not a full semantic judge."""
    rubric = case['rubric']
    text = flatten_text(texts).casefold()
    checks = [{'name': 'source_valid', 'passed': bool(source_valid)},
              {'name': 'output_size', 'passed': len(text) <= rubric['max_output_chars']},
              {'name': 'no_code_dump', 'passed': chr(96)*3 not in text}]
    if rubric['empty_output']:
        checks.append({'name': 'noise_not_saved', 'passed': not text.strip()})
    for index, alternatives in enumerate(rubric['required_concepts']):
        checks.append({'name': f'concept_{index + 1}',
                       'passed': any(term.casefold() in text for term in alternatives),
                       'alternatives': alternatives})
    for claim in rubric['forbidden_claims']:
        checks.append({'name': 'no_claim:' + claim, 'passed': claim.casefold() not in text})
    return {'id': case['id'], 'category': case['category'],
            'passed': all(check['passed'] for check in checks), 'checks': checks}


def make_messages(case):
    from harvest import redact
    result = []
    for index, turn in enumerate(case['messages']):
        identity = hashlib.sha256(f'{case["id"]}:{index}'.encode()).hexdigest()
        result.append({'id': identity, 'role': turn['role'], 'text': redact(turn['text']),
                       'timestamp': f'2026-11-10T08:{index:02d}:00Z', 'source': 'codex',
                       'path': f'synthetic/{case["id"]}.jsonl', 'project': 'Synthetic ' + case['id'],
                       'session_id': case['id'], 'project_id': 'synthetic/' + case['id']})
    return result


def evaluate_one(case, generate, adapter):
    started = time.monotonic()
    messages = make_messages(case)
    response = None
    try:
        if adapter == 'legacy':
            import knowledge
            response = generate(messages, {})
            normalized = knowledge._validate_updates(response, messages)
            texts = [fact[1] for fact in normalized]
        else:
            import knowledge_pipeline
            session = {'session_id': case['id'], 'project_id': 'synthetic/' + case['id'],
                       'messages': messages, 'fingerprint': hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()}
            response = generate(session)
            normalized = knowledge_pipeline.validate_summary(response, session)
            texts = normalized
        result = grade_case(case, texts)
        result['output'] = response
    except Exception as error:
        result = grade_case(case, [], source_valid=False)
        # Any execution/schema error fails the case even if its expected output was empty.
        result['passed'] = False
        result['error'] = f'{type(error).__name__}: {error}'
        result['output'] = response
    result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Run configured API on synthetic examples only')
    parser.add_argument('--adapter', choices=['legacy', 'pipeline'], default='legacy')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.live:
        parser.error('Use --live to explicitly authorize synthetic API evaluation')
    if not 1 <= args.workers <= 4:
        parser.error('workers must be between 1 and 4')
    corpus_path = Path(__file__).with_name('knowledge_cases.json')
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    if args.adapter == 'legacy':
        from knowledge import api_generator
        generate = api_generator(ROOT)
    else:
        generate = importlib.import_module('knowledge_pipeline').api_summarizer(ROOT)
    started = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(evaluate_one, case, generate, args.adapter) for case in corpus['cases']]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f'{len(results)}/{len(futures)} {result["id"]}: {"PASS" if result["passed"] else "FAIL"}', flush=True)
    order = {case['id']: index for index, case in enumerate(corpus['cases'])}
    results.sort(key=lambda result: order[result['id']])
    checks = [check for result in results for check in result['checks']]
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'adapter': args.adapter,
              'model': 'claude-haiku-4-5-20251001' if args.adapter == 'legacy' else 'configured pipeline model',
              'corpus_sha256': hashlib.sha256(corpus_bytes).hexdigest(),
              'grader_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'workers': args.workers, 'case_count': len(results),
              'cases_passed': sum(result['passed'] for result in results),
              'checks_total': len(checks), 'checks_passed': sum(check['passed'] for check in checks),
              'elapsed_seconds': round(time.monotonic() - started, 3), 'results': results,
              'limits': 'Synthetic fixed development corpus. Concept/forbidden-claim rules are not full semantic judging. Live model outputs are stochastic.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Cases: {report["cases_passed"]}/{report["case_count"]}; checks: {report["checks_passed"]}/{report["checks_total"]}', flush=True)
    print(f'Report: {args.output}', flush=True)


if __name__ == '__main__':
    main()
