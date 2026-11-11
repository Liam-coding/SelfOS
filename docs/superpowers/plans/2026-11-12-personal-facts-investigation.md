# Personal-fact investigation (#9)

1. Compare canonical and staging snapshots with read-only aggregate statistics. Verify selected domains, saved summary fields, retained records, historical records and dashboard count logic. Do not copy private facts, model-review explanations or source files into Git.
2. Trace interruption behavior through run_knowledge and install_rebuilt. Reproduce a staged personal fact that remains absent from canonical counts until a successful transaction. Use a synthetic fixture and no model call.
3. Create an independent anonymous holdout for the record validation/retention boundary, including explicit attributes, assistant suggestions, quoted material, project requests, temporary observations, old facts, exclusions and invalid evidence. Evaluate actual validate_record/merge_records behavior, not scripted expected verdicts. Report precision/recall/traceability for this boundary only; do not describe these as model extraction metrics.
4. Document source attribution, stable relation keys, scope, temporal observations/conflicts and conservative abstraction rules with input/output examples. Do not target a record count.
5. Record confirmed gaps as focused follow-up issues. Publish a tested investigation PR; explicitly distinguish the observed canonical/staging mismatch from extraction quality that requires separate model evaluation.

Review focus: no private data in artifacts; holdout labels independent of computed output; stage metrics must not be presented as end-to-end model quality; no incomplete staging installation; existing frozen acceptance files stay byte-identical.
