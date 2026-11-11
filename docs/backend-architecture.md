# Python backend architecture

The backend lives in an installable package under src/selfos. Root Python files preserve existing commands and imports; new backend code imports the owning package module directly.

| Package | Responsibility | Examples |
| --- | --- | --- |
| app | Use cases, incremental/rebuild orchestration, retry diagnostics, jobs and chat context | knowledge.py, pipeline.py, jobs.py |
| sources | Local conversation discovery, parsing, workspace identity and session partitioning | conversations.py, readers.py, workspaces.py, compaction.py |
| knowledge | Evidence contracts, input filtering, classification, project merge, personal records, history and scoring | contracts.py, evidence.py, filtering.py, projects.py, records.py |
| storage | Safe file access, atomic writes, locks, journals, checkpoints, backup/restore and managed Markdown | files.py, pipeline.py, legacy.py, documents.py, records.py, settings.py |
| providers | Model factories, response protocols, evidence review, model configuration and proxy transport | knowledge.py, client.py, settings.py, reviews/ |
| security | Credential verification, local recovery, sessions and private file permissions | auth.py |
| web | HTTP composition, authentication/request adapters and rendering integration | server.py, routes/, rendering/ |
| resources | Public authentication locales, empty onboarding templates and the digest skill | locales/, templates/, skills/ |

## Dependency direction

CLI and HTTP adapters invoke application services. Application services compose source adapters, providers, domain rules and storage. Providers use domain schemas and validation; storage uses domain identities and rendering rules without calling models. Domain and storage modules never import application services, routes or CLI files.

Source parsers normalize conversation records containing identity, role, text, timestamp, source path, project identity and session identity. Knowledge filtering decides how to compact transient requests, code and runtime evidence; source parsers do not choose what durable knowledge to retain. Existing record formats and schema validators remain the shared contracts.

All package imports, including function-local imports, must be acyclic. The architecture tests enforce this direction. Function-local imports remain where a model factory or optional path benefits from deferred loading; they no longer hide circular dependencies.

HTTP route mixins receive a runtime context from the server composition root. Background progress helpers accept explicit state, lock and heartbeat parameters; chat projection accepts an explicit vault. Existing serve module globals remain available through the compatibility facade. The giant dashboard string and existing browser assets remain in web/rendering; splitting those belongs to frontend Issue #30.

## Paths and resources

AppPaths owns the resolved project root, vault, dashboard, model configuration, environment file and authentication marker. The platform authentication directory is also defined in paths.py. Authentication hashes remain in their existing private OS directory; this refactor does not migrate or reset credentials.

- Legacy script commands default to their checkout directory, even when launched from another working directory.
- Installed commands default to the working directory, or SELFOS_ROOT when set. Every command supports an explicit --root.
- Knowledge also retains --vault for an independently selected vault.
- Explicit --root selects model configuration even with an external --vault. Legacy --vault-only commands continue reading model configuration from the vault's parent.
- Package resources are read with importlib.resources. A new installation receives empty templates, never the repository's example or personal vault contents.
- HTTP workers launch python -m selfos with an explicit root and vault; they do not require scripts inside the data directory. The subprocess environment carries the package import location independently of the data root.

Existing vault paths, source indexes, checkpoints, staging boundaries, journals and backup formats are unchanged. There is no data migration.

## Installation and commands

From a checkout:

    python -m pip install -e .
    python serve.py --port 7070
    python knowledge.py --help
    python harvest.py --help
    python selfos_auth.py reset

Installed commands can use a separate data directory:

    selfos-serve --root /path/to/my-selfos --port 7070
    selfos-knowledge --root /path/to/my-selfos --help
    selfos-harvest --root /path/to/my-selfos --help
    selfos-auth reset --root /path/to/my-selfos

Equivalent module commands are python -m selfos serve, knowledge, harvest or auth followed by the same options. Password reset remains an interactive local command.

## Compatibility and verification

Root modules are thin entry points. The isolated _compat and _legacy modules forward legacy symbols to their actual owners, including assignments used by existing integrations and tests. Internal package code never uses these facades. Prefer injecting the explicit parameters or patching the owning package in new tests.

Run python -m pytest -q. Boundary tests cover import direction, cycles, legacy exports, foreign working directories, resource availability and package subprocess commands. HTTP regressions cover authentication, local-origin checks, progress, cancellation and resume. Knowledge regressions use synthetic conversations and temporary vaults; frozen evaluation files and original conversations are not rewritten.

Build a wheel with python -m pip wheel . --no-deps. Validate the installed artifact from a directory outside the checkout, including authentication resources and HTTP actions. Program regressions and model-quality evaluations remain separate; a backend refactor does not require a full production import.
