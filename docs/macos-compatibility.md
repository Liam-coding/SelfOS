# macOS compatibility investigation

This report separates executed checks from source inspection and desktop behavior that has not been tested. It does not claim complete macOS support from a green Windows suite.

## Evidence collected

Initial run: https://github.com/Liam-coding/SelfOS/actions/runs/43074558430

The Intel runner reported macOS 15.7.9 and x86_64. Python 3.10.21 and 3.12.10 each completed all 620 regression tests. The independently installed wheel then failed its transaction check with pipeline path escapes vault. The remaining original Apple Silicon jobs were cancelled after this defect was reproduced and corrected; they do not count as a pass or a failure. The corrected run supersedes that run.

The failure revealed a real boundary-normalization bug: a resolved destination was compared against an unresolved vault. macOS temporary paths can alias /private/var through /var; relative vault paths have the same inconsistency on other systems. The fix canonicalizes the vault before pipeline writes, recovery and containment checks. Nested source/file symlinks that escape the canonical vault remain rejected. Dedicated relative-path regressions reproduce the old failure; existing escape tests continue to exercise the security boundary.

Corrected run: https://github.com/Liam-coding/SelfOS/actions/runs/43075870012

All four corrected jobs completed successfully for commit fa0ec13 on 2026-11-12. These are GitHub-hosted macOS runners, not physical-user machines; exact CPU models and native Safari versions were not measured.

| Actual macOS | Architecture | Python | Regression suite | Installed verifier | Browser fixtures |
| --- | --- | --- | --- | --- | --- |
| 15.7.9 | x86_64 | 3.10.21 | 623 passed | Passed | Chromium and WebKit passed |
| 15.7.9 | x86_64 | 3.12.10 | 623 passed | Passed | Chromium and WebKit passed |
| 15.8.2 | arm64 | 3.10.11 | 623 passed | Passed | Chromium and WebKit passed |
| 15.8.2 | arm64 | 3.12.10 | 623 passed | Passed | Chromium and WebKit passed |

Browser automation used Playwright 1.65.0, Chrome for Testing 158.0.8127.18, and Playwright WebKit 27.2. Each engine tested 1440x900 and 390x740 viewports. Logs and screenshots are available in that run's compatibility artifacts. HTTP browser responses were intercepted fixtures; authenticated real local HTTP was verified separately by the installed package verifier.

Recommended scope: the core package and fixture workflows are verified on the four environments above. Other macOS/Python versions and physical desktop integration remain unverified. Physical-machine validation is tracked separately in #35: https://github.com/Liam-coding/SelfOS/issues/35

## Compatibility checklist

| Area | Current evidence | Limit |
| --- | --- | --- |
| Editable installation and dependencies | Passed in all four corrected jobs | Intel Argon2 bindings may build from source; hosted runners provide build tools |
| Full backend regression suite | 623 passed in each corrected job | Fixture-based tests do not prove external model behavior |
| Module subcommands and resources | Four module command help paths and resources passed from an independent wheel installation | Actual command startup/browser launch is separate; console-script invocation is not covered by this verifier |
| Claude Code/Codex discovery | Source code uses portable home paths and configurable CODEX_HOME/CLAUDE_CONFIG_DIR | Synthetic parsing is tested; no personal source directories were scanned |
| Auth paths/permissions | macOS auth-directory assertion and 0700 directory/0600 hash permissions passed in all four installed checks | Keychain integration is not implemented or claimed |
| Atomic writes, lock ownership, backups and restore | Corrected macOS suite and installed transaction/restore checks passed, including relative and symlinked vault roots | System crash/power loss is not reproduced by these checks |
| Stop/resume/concurrency/disconnect | Existing HTTP/job regressions use synthetic fixtures | Physical sleep/wake needs desktop validation |
| Model direct/manual proxy modes | Configuration and transport have fixture coverage | No real provider request or model key was used |
| macOS automatic static proxy | Code calls urllib.request.getproxies after checking environment proxies | Actual System Settings proxy behavior and bypass rules are not verified; PAC is not supported |
| Chromium/WebKit dashboard | Both engines passed desktop/mobile settings, language/theme, knowledge search/detail/source checks in all jobs | These are intercepted fixture UI checks; Playwright WebKit is not Safari |
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
