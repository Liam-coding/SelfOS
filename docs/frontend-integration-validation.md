# Reproducing integrated frontend checks

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
