# Knowledge quality and first-use implementation plan

Goal: finish #40, then #38, #15, #47 and #24 in that order.

Architecture: retain one-pass session extraction, pure domain validation/merge modules, atomic vault transactions and packaged localized browser resources. Extend shared provenance and correction contracts before adding UI mutations. Use isolated synthetic vaults and mocked endpoints; no full production import.

## Ordered deliverables

- [ ] #40: source-backed explicit preference revision/validity protocol and validation, conservative chronology, durable correction preservation, independently labeled source-session evaluation fixtures, Markdown/browser display. Test late arrivals, ties, unsupported dates, quoted AI, scope, replay, backups and cancellation. Run full suite and browser checks; independent review; PR.
- [ ] #38: direct versus contextual evidence, typed personal applicability and semantic retention, independent source-session scoring distinct from structural contracts. Address frozen candidate failures without modifying frozen expectations. Run focused/full regression and review; PR.
- [ ] #15: domain correction/suppression ledger and stable source-based record identity; atomic edit/delete/merge/undo service and authenticated API; localized accessible browser controls. Verify repeat import/rebuild, conflicting new evidence, interruptions and provenance preservation; review; PR.
- [ ] #47: reproducible integrated browser suite covering auth, settings, search/sources, timelines, stop/resume/reload, language switching, mobile, theme/accessibility and installed wheel. Fix confirmed failures; report exact tested commit/platform limits; PR.
- [ ] #24: recoverable first-use setup flow using existing source/config/import services, bounded preview/sample action, exclusions and connection feedback, persisted skip/resume, localized UI. Test fresh/existing profiles and synthetic browser; review; PR.

Requirements: GitHub issue bodies are authoritative. Never equate deterministic fixture/model-response mocks with measured model extraction precision. Independently labeled sessions and an optional bounded evaluator can be supplied without invoking a live model or claiming unmeasured gains. Keep historical sources and backups untouched. Do not close an issue until its requirements are proved; document remaining work candidly.

Execution: use executing-plans inline and test-driven-development; dispatch only skill-required read-only reviews. The recurring merge goal has resumed; publish and merge reviewed changes after CI passes, then continue in the requested issue order. Live model evaluation remains subject to the separately requested bounded authorization.
