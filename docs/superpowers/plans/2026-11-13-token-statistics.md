# Token statistics implementation plan

User narrows PR #66 to actual token statistics, without prices. Existing request allowance/resume remains. Workload prediction is deferred.

Architecture: provider responses feed the durable per-checkpoint journal; authenticated usage-only GET serves bounded metadata; progress UI polls while imports run. No model calls or source scans for status. Preserve current privacy and quality-report behavior.

- [x] RED: reject price patches; legacy prices ignored; no price/preview UI; live progress displays usage and failures before completion; count Anthropic and OpenAI cache tokens; actual transport model identity.
- [x] Remove preview and prices; persist only request limits; use transport identity and explicit cache counters.
- [x] Add authenticated usage-only route and progress polling, including recovery and finish.
- [x] Run targeted, full regression and English/Chinese browser checks. Independent review, update PR #66 around final scope, retain #22 open for deferred estimation.

Validation: 1050 passed, 1 optional browser skipped; browser/auth/token run 7 passed; independent review 24 backend + 1 browser passed, no remaining Critical/Important.
