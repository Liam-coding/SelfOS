# Reproducing integrated frontend checks

## Recorded validation: 2026-11-13

Tested implementation: 8b59290d5dcab598d3af8faba61ae8dbc01159f0, based on merged main 4561dfa01ec838acd1aad178dab99a46aeff22a2. This commit records the implementation bytes used in the checks; the subsequent report update changes documentation only.

| Check | Result |
| --- | --- |
| Full Python unit/contract suite | 899 passed, 132.70 seconds |
| Checkout Chromium matrix | Four cases passed |
| Installed wheel, foreign cwd, final matrix | Four cases passed |
| Source vs installed application | 154 Python/resource files byte-identical |
| Frozen acceptance inputs | All five hashes unchanged |
| Independent review | Three Important findings and source-filter gap fixed and re-reviewed |

Environment: Windows build 26300, Python 3.11.7, Chromium 135.0.7049.95. Wheel SHA-256: 60bf9a771115bb1196502bd29946440590c4e3982280898541ff288ec1b9cfe4. No real-model evaluation was performed.

Each output directory contains results.json, per-case JSON and screenshots named en-1280-light-no-preference.png, zh-CN-390-dark-reduce.png, zh-CN-1280-dark-no-preference.png and en-390-light-reduce.png. The desktop case used six local fixture requests: two connection checks, two session extractions and two project syntheses; its resume did not re-extract the first saved session. Other matrix cells used two connection-check requests each.

This explicitly invoked browser suite validates the merged application for #47. It is optional and does not run on every pull request. Ordinary unit/contract checks remain python -m pytest -q.

Install Playwright and Chromium in your test environment:

~~~sh
python -m pip install playwright
python -m playwright install chromium
python tests/browser/frontend_integration.py --browser /absolute/path/to/chromium --output /absolute/path/to/results
~~~

The browser executable is explicit so a report can identify the browser actually tested. Results and screenshots are written to the output directory; temporary application data, passwords and source profiles are discarded. The suite asserts that the imported package belongs to the selected checkout or installation directory.

## Installed-wheel execution

~~~sh
python -m pip wheel . --no-deps --wheel-dir /absolute/path/to/wheels
python -m pip install --no-deps --target /absolute/path/to/installed /absolute/path/to/wheels/selfos-0.5.0-py3-none-any.whl
cd /a/different/working/directory
python /absolute/path/to/repo/tests/browser/frontend_integration.py --package-path /absolute/path/to/installed --browser /absolute/path/to/chromium --output /absolute/path/to/installed-results
~~~

The active Python environment must also have the package runtime dependencies, including argon2-cffi. Test utilities remain outside the wheel.

## What the suite exercises

| Workflow | Evidence |
| --- | --- |
| Access protection | Wrong and correct passwords, protected knowledge API, actual page logout |
| Language and presentation | English fallback, Chinese, desktop/mobile, light/dark, reduced motion and no horizontal overflow |
| Overall | Keyboard activation reaches the dimension cards |
| Model/network | Configuration loading, provider/proxy form, unsaved input/focus across language changes, local failed and successful structured connection checks |
| Knowledge browser | Search, source/date filters, pagination and original conversation navigation |
| Timeline | Pagination and decisions filter against synthetic decision/progress history |
| Import lifecycle | Real child CLI and SSE, saved first session, gated second response, locale switch, reload/status recovery, stop and resume, final publication and checkpoint reuse |
| Integrity | Source bytes unchanged, no page errors or external browser requests, fresh runtime state per profile |

The matrix uses 1280-pixel desktops and 390-pixel mobile viewports with both locales and themes. The full import lifecycle runs once on desktop; it is not claimed as independently repeated in each matrix cell.

## Fixture boundaries

The model is a deterministic loopback HTTP endpoint, with an exclusively synthetic API key. A test-only child bootstrap restricts discovery to its marked temporary source directory before invoking the real knowledge CLI. Subprocesses, streams, source parsing, checkpoints, stop markers, synthesis, publication, authentication and packaged rendering remain real application code. This validates application integration, not extraction quality from a real model or normal home-directory discovery. No private session scan or paid model request runs.

Windows and Chromium checks do not establish macOS, Safari or native mobile support. Those platforms need separate verification. Failed runs retain the failing stage in the case JSON; cleanup releases model gates and stops children and servers.
