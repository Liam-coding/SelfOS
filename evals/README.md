# Knowledge acceptance baseline

The acceptance contract was frozen before implementation on 2026-11-10. The conversation-to-knowledge pipeline is now implemented. The original 85 capability cases remain active; their corpus, rubric and contract hashes are preserved in knowledge_acceptance_manifest.json.

## Test layers

- Existing regression suite: 145 tests in test_harvest.py and test_knowledge.py.
- Frozen new acceptance contract: 85 cases in tests/test_project_knowledge_contract.py.
- Evaluation ruler: 13 tests in tests/test_knowledge_eval_grader.py.
- Live synthetic dialogue corpus: 24 cases in knowledge_cases.json. No personal sessions are used.

Run all program tests with `python -m pytest -q --junitxml=program-results.xml`. The historical pre-development result was 158 passed, 85 failed, with no collection errors. The 85 failures named missing capabilities; they were not an estimate of model quality. Additional regression tests now cover source validation, session/synthesis protocols, cancellation, transactional restore, history reconstruction, retained manual notes and the local HTTP/browser contract.

Run the legacy live baseline with:

```
python evals/run_knowledge_eval.py --live --adapter legacy --workers 3 --output quality-results.json
```

The implemented knowledge_pipeline module provides the contract interfaces and `api_summarizer(root)`, delegating to the actual prepared-session summarizer. Evaluate the current implementation with `--adapter pipeline`; use an output path outside your vault.

The most recent two fixed-corpus development runs scored 23/24 cases with 162/166 and 165/166 checks respectively. Independent multi-project holdouts still showed intermittent context omissions. These are separate from program-test pass rates, are not guarantees, and should be rerun on your configured model without changing the frozen ruler.

## Frozen baseline

- Complete live cases: 18/24 (75%).
- Automated check points: 153/166 (92.2%).
- Four cases failed at JSON parsing; two lost a material qualification or next step.
- Before freezing, review corrected two legitimate rubric defects: pending measurement was missing from benchmark alternatives, and caching was missing as a grammatical variant of cache. The same captured outputs were regraded offline; conversation inputs and model calls were unchanged. The initial result was 17/24 and remains archived. This score change is a ruler correction, not an implementation improvement.
- Hashes and correction reasons live in knowledge_acceptance_manifest.json.

These checks use explicit concept alternatives, forbidden claims, provenance and size constraints. They do not replace human semantic review, verify arbitrary factual entailment, or prove performance on unseen personal conversations. Keep the fixed development set unchanged and report a separate post-development holdout sample.

## Reporting after development

Report existing regressions, new capability acceptance and live dialogue quality separately. Compare per-case missing concepts, source errors, cached-call counts and compression tests. Retain all failed cases and record any justified test correction with a new baseline. Do not tune expected answers to generated outputs.
