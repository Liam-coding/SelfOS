# Continuous integration

Ordinary code pull requests run one Ubuntu/Python 3.12 unit and contract test job. README, license and docs-only changes complete that job without installing dependencies or running tests. A new commit cancels an older run for the same branch or pull request.

The four-job macOS compatibility matrix is opt-in for pull requests. Add the **ci:macos** label when a change needs Apple Silicon/Intel, installed-package, Chromium and WebKit verification. It can also be started from Actions using **Run workflow** and runs weekly on Sunday at 00:00 UTC.

The heavy matrix still executes the complete regression suite, installed-wheel checks and browser fixtures when requested. It no longer runs automatically for every ordinary pull request.

For branch protection, require **Tests / Unit tests** as the everyday check. Keep the optional macOS matrix out of unconditional required checks, since those jobs intentionally skip unless requested. Passing the lightweight job does not imply the optional macOS checks ran.
