# macOS compatibility investigation

This report separates executed checks from source inspection and desktop behavior that has not been tested. It does not claim complete macOS support from a green Windows suite.

## Evidence collected

Initial run: https://github.com/Liam-coding/SelfOS/actions/runs/43074558430

The Intel runner reported macOS 15.7.9 and x86_64. Python 3.10 completed all 620 regression tests. The independently installed wheel then failed its transaction check with pipeline path escapes vault. The same installed-wheel step also failed on the Intel Python 3.12 job. Apple Silicon jobs were still pending when this initial result was recorded.

The failure revealed a real boundary-normalization bug: a resolved destination was compared against an unresolved vault. macOS temporary paths can alias /private/var through /var; relative vault paths have the same inconsistency on other systems. The fix canonicalizes the vault before pipeline writes, recovery and containment checks. Nested source/file symlinks that escape the canonical vault remain rejected. Dedicated relative-path regressions reproduce the old failure; existing escape tests continue to exercise the security boundary.

Final verification results will be added after the corrected macOS runs complete.

## Compatibility checklist

| Area | Current evidence | Limit |
| --- | --- | --- |
| Editable installation and dependencies | Passed on Intel macOS in the initial run | Apple Silicon and final fixed artifact verification pending |
| Full backend regression suite | 620 passed on Intel Python 3.10 in the initial run | Fixture-based tests do not prove external model behavior |
| Module/console startup paths and resources | Installed verifier reaches the transaction check | Full installed verification pending corrected run |
| Claude Code/Codex discovery | Source code uses portable home paths and configurable CODEX_HOME/CLAUDE_CONFIG_DIR | Synthetic parsing is tested; no personal source directories were scanned |
| Auth paths/permissions | Darwin branch uses Library/Application Support/SelfOS; POSIX code applies 0700/0600; installed verifier checks these | Keychain integration is not implemented or claimed |
| Atomic writes, lock ownership, backups and restore | Existing regression coverage; installed check uncovered and reproduces alias-path bug | Corrected real macOS result pending |
| Stop/resume/concurrency/disconnect | Existing HTTP/job regressions use synthetic fixtures | Physical sleep/wake needs desktop validation |
| Model direct/manual proxy modes | Configuration and transport have fixture coverage | No real provider request or model key was used |
| macOS automatic static proxy | Code calls urllib.request.getproxies after checking environment proxies | Actual System Settings proxy behavior and bypass rules are not verified; PAC is not supported |
| Chromium/WebKit dashboard | Reproducible installed-package browser fixture verifier added | Actual macOS results pending; Playwright WebKit is not Safari |
| Desktop Safari and browser auto-launch | Not tested | Must be tested on a physical Mac in a separate user profile |

## Reproduce without personal imports

Run these commands from a clean checkout with Python 3.10 or newer:

    python -m pip install -e . pytest
    python -m pytest -q --tb=short
    python -m pip wheel . --no-deps -w dist
    python -m pip install --target ./installed-check dist/selfos-*.whl
    python tools/verify_platform.py ./installed-check
    python -m pip install playwright
    python -m playwright install chromium webkit
    python tools/verify_browser.py ./installed-check ./browser-reports chromium
    python tools/verify_browser.py ./installed-check ./browser-reports webkit

The package verifier uses temporary roots, a private temporary authentication directory, a single synthetic JSONL file, and fixture backup/restore. It never discovers default conversation roots or calls a model. The browser verifier intercepts HTTP responses with synthetic fixtures; its screenshots contain no personal knowledge.

The macOS workflow records actual OS version, CPU architecture and Python version and uploads logs/JUnit/screenshots. Treat physical-machine proxy, Safari and sleep/wake work as separate from these checks. Do not reset or overwrite an existing user's password/configuration to perform compatibility testing.
