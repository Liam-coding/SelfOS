# Package-only commands

User-approved scope: remove the remaining four root scripts and use python -m selfos or installed console commands. Update the existing cleanup PR rather than introducing another unrelated PR.

Steps: add failing root/command tests; migrate test imports and patch lookup sites to owning modules; move frozen-evaluator aliases into evals/adapters; remove unused application compatibility infrastructure; update installation and command documentation; run full regressions and review; back up local removals and preserve vault/config/auth/dashboard data.
