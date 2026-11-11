# Repository root cleanup

Goal: keep only serve.py, knowledge.py, harvest.py and selfos_auth.py as compatible commands; remove other root Python facades and stop tracking generated dashboard.html.

Constraints: preserve existing commands and local dashboard/vault/auth data; ordinary tests import owning selfos modules; frozen evaluation files remain byte-identical. Compatibility for the frozen evaluator belongs under evals/adapters, accessed via a new launcher and test setup rather than root files.

1. Add failing root-layout and evaluation-launcher tests.
2. Migrate ordinary imports and patches to owning package modules; remove unused facades and narrow compatibility exports to four commands.
3. Add an evaluation-only adapter and launcher, preserve frozen test/corpus bytes, and remove dashboard.html from tracking while retaining local output.
4. Run all regressions, synthetic non-live evaluator, CLI/resource checks and independent review. Update docs and create a follow-up PR.
