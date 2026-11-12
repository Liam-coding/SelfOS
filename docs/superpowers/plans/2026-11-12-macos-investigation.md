# macOS compatibility investigation (#8)

Use actual macOS runners and isolated fixtures; do not infer support from Windows results. Preserve production behavior and personal data.

1. Audit paths, source discovery, proxy selection, authentication permissions, atomic storage, locks and child commands. Record code evidence separately from executed checks.
2. Add a portable installed-wheel verifier under tools. Require its installed-package path argument, run from a temporary data directory, and exercise four command help paths, neutral resources, synthetic source parsing, backup/restore and authenticated HTTP/settings/logout. Record OS, architecture and Python metadata. Never call a model or discover default conversation roots.
3. Add a macOS CI matrix for Intel and Apple Silicon, Python 3.10 and 3.12. Run the full regression suite and installed-wheel verifier. Upload machine metadata, JUnit and logs even after failures. Use read-only repository permissions and pinned checkout/runtime actions.
4. Inspect actual runs. Fix confirmed portability regressions with failing tests; keep other defects in focused follow-ups. Publish a pass/fail/not-tested compatibility checklist and reproducible commands. Safari, real proxy configuration and physical sleep/resume require explicit separate validation; CI cannot prove them.

Review focus: wheel imports must not resolve to the checkout; no model/API secret use; no source discovery beyond the fixture; private auth directory is temporary; platform/version claims must link actual run evidence.
