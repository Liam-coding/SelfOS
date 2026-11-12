# SelfOS

[English](README.md) | [简体中文](README.zh-CN.md)

[![README views](https://hits.sh/github.com/Liam-coding/SelfOS.svg?style=flat&label=README%20views&color=2563eb)](https://hits.sh/github.com/Liam-coding/SelfOS/)

**Turn AI conversations into knowledge you can use again.**

SelfOS is a local, Markdown-based personal knowledge system. It organizes your Claude Code and Codex conversations into facts, preferences, project context and reusable experience, so your AI assistant can understand what you are working on across sessions.

![SelfOS knowledge overview and browser](examples/selfos-demo/selfos-en.png)

*Core dashboard with example data.*

[Browse the bilingual synthetic demo](examples/selfos-demo/README.md) or open its HTML pages locally. All demonstration data is fictional.

## Quick start

For tested macOS environments and reproducible checks, see the [macOS compatibility report](docs/macos-compatibility.md).

Requires **Python 3.10+**, Git, and an Anthropic Messages or OpenAI-compatible Chat Completions API for organizing and chat. Local models need tool support. Password hashing uses argon2-cffi; install it with `python -m pip install -r requirements.txt`.

1. Clone the repository:

    ```bash
    git clone https://github.com/Liam-coding/SelfOS.git
    cd SelfOS
    python -m pip install -e .
    ```

2. Optionally create `.env` for Anthropic, or configure your model on the dashboard after starting it:

    ```dotenv
    ANTHROPIC_API_KEY=your-api-key
    # Optional, for a compatible gateway:
    # ANTHROPIC_BASE_URL=https://your-api-endpoint
    ```

3. Start the local dashboard:

    ```bash
    python -m selfos serve
    ```

    Open [http://localhost:7070](http://localhost:7070).
    Log in before accessing the dashboard. Existing vaults require local password initialization with `python -m selfos auth reset`; an empty installation can set its password on the login page. See [authentication](docs/authentication.md).
    Select **Settings > Model and network** to choose the interface, Base URL, model, API key and proxy. Use **Save and test connection** before importing. See [model settings](docs/model-settings.md).

    The interface defaults to English. Choose **Settings > Language** for Simplified Chinese.

4. Select your focus domains and detail level under **Choose what matters**, then click **Organize my knowledge**. When the operation completes, use **Browse knowledge** to explore records and their sources.

Before using the vault as agent context, review `vault/PROFILE.md`, `vault/NOW.md` and `vault/GOALS.md` and personalize their contents.

## What SelfOS keeps

| Category | What belongs here |
| --- | --- |
| Personal facts | Explicit statements about your circumstances, linked to source evidence |
| Preferences | Enduring choices; superseded choices move to history |
| Projects | Goals, current state, decisions, blockers and next steps |
| Reusable experience | Reasoning and methods with applicability and limits |
| History | Earlier project states, meaningful outcomes and scoped observations |

You choose the domains and wording detail. Retention follows meaning and evidence, with no target number of final records. Local measurements and configurations stay scoped to their projects rather than becoming universal advice.

Use global search to find records across all categories, filter by project context,
source or date, and inspect matching excerpts and original evidence. See the
[search guide](docs/knowledge-search.md).

## How importing works

SelfOS reads supported local JSONL conversations, filters transient requests and runtime noise, and compacts code and bulk data **only in model input**. It extracts sourced records from session parts, then reviews and consolidates project knowledge.

Three API workers process session parts by default; saves are serialized. Successful work is checkpointed locally. Canonical knowledge is updated only after the complete operation succeeds, with transaction backups. **Original conversations are never rewritten**, and manual notes outside managed sections are preserved.

For a scan without API calls or knowledge writes:

```bash
python -m selfos knowledge --dry-run
```

See the [import and recovery guide](docs/knowledge-import.md) for CLI options, source validation, retries and storage details.

## Stop, resume and undo

- **Stop:** click the stop button. Active requests may still finish saving; wait for the stopped status before closing the server.
- **Resume:** click Organize my knowledge again. Unchanged successful checkpoints are reused. Refreshing or losing the stream also requests cooperative stopping; the page follows the existing saving/stopped task, and remaining work resumes on your next click.
- **Undo:** use the dashboard's undo action or `python -m selfos knowledge --restore-last`. Restore rejects later file edits so it does not overwrite newer changes.

On the next import, changed retention settings trigger a rebuild under the new policy. Completed staging work and backups remain available for recovery; see the [guide](docs/knowledge-import.md#stop-retry-and-restore).

## Use the knowledge with your AI agent

Your vault combines generated knowledge with Markdown you maintain yourself:

| Path | Purpose |
| --- | --- |
| `vault/PROFILE.md`, `vault/NOW.md`, `vault/GOALS.md` | Personal background, current priorities and goals |
| `vault/02_Work/projects/` | Generated project cards |
| `vault/05_Life/lessons.md` | Reusable experience |
| `vault/knowledge/` | Personal facts, preferences and history |
| `vault/91_Staging/` | Manual agent proposals awaiting review |

Claude Code, Codex and other file-reading agents can use these files as context. Follow the [agent integration guide](docs/agent-integration.md) for setup. Manual agent edits can use the proposal/review workflow; one-click imports use the automatic, backed-up flow described above.

The separate Harvest workflow remains available with `python -m selfos harvest` for conversation digests, staging proposals and the seven-dimension life overview. Details are in the [development guide](docs/dev.md).

## Data use and current limits

Markdown storage and source paths stay local. **Organizing and chat send redacted text and relevant context to your configured API.** Local storage does not imply offline inference, and redaction cannot guarantee removal of every sensitive detail.

Source references make records traceable; AI summaries and candidate reviews do not independently prove accuracy. Multi-project conversations can still lose context. Supported inputs are local Claude Code and Codex JSONL sessions, including supported migrated archives; other chat-export formats are not yet integrated.

## Documentation and contributing

| Guide | Covers |
| --- | --- |
| [Import and recovery](docs/knowledge-import.md) | Retention rules, CLI, checkpoints, retries and backups |
| [Project timelines](docs/project-timelines.md) | Trace goals, decisions, progress and blockers to recorded conversations |
| [Knowledge corrections](docs/knowledge-corrections.md) | Edit, delete, merge and undo while preserving sources and respecting later imports |
| [Agent integration](docs/agent-integration.md) | Connecting Claude Code, Codex and other agents |
| [Development](docs/dev.md) | Architecture, endpoints and Harvest workflows |
| [Backend package](docs/backend-architecture.md) | Module boundaries, installation, paths and compatible commands |
| [Frontend structure](docs/frontend-architecture.md) | Packaged templates, styles, browser modules and UI/backend contracts |
| [Internationalization](docs/internationalization.md) | Locale catalogs, adding translations and preserving state during language changes |
| [Evaluation](evals/README.md) | Frozen acceptance cases and model-quality checks |

To run program tests:

```bash
python -m pip install pytest
python -m pytest -q
```

Contributions are welcome, especially new source formats, agent integrations and retention-quality improvements. Keep program-test results and model-quality scores separate, and preserve the frozen evaluation inputs.

Created by [Liam (Jialei Liu)](https://github.com/Liam-coding). Licensed under [MIT](LICENSE).
