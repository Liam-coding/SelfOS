# Model and network settings

New users can configure the same form through the [bounded first-run guide](first-run-onboarding.md); opening the guide does not test or call the model automatically.

Start `python -m selfos serve`, open the dashboard, and select **⚙ Settings → Model and network**.
Language is available in the same settings dialog. New visitors default to English; saved language choices are retained.
The configuration is shared by conversation imports, project refinement, optional AI staging
and dashboard chat. Existing Anthropic `.env` settings work until settings are saved on the page.
Without an explicit model, existing Claude defaults remain; an explicit model applies to all tasks.

| Interface | Base URL | Model example |
| --- | --- | --- |
| Anthropic Messages | `https://api.anthropic.com` | `claude-haiku-4-5-20251001` |
| OpenAI-compatible Chat Completions | `https://api.openai.com/v1` | `gpt-4.1-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Local Ollama | `http://localhost:11434/v1` | An installed model with tool support |

Other services exposing Chat Completions can use OpenAI-compatible. Set the exact model
identifier offered by the service. Knowledge extraction requires function/tool calls; endpoint
compatibility alone does not guarantee extraction quality. Existing source validation, retries,
checkpoints and rollback still apply.

**Save and test connection** saves the form and sends one small, potentially billable request
containing synthetic test text. It verifies network access, authentication and a structured tool
result without sending vault contents or starting an import. A failed test leaves settings saved.

## Proxy modes

- **Auto:** use `HTTPS_PROXY` / `HTTP_PROXY` (or `ALL_PROXY`) first. On Windows, fall back to
  the static system proxy in the registry. Preserve `NO_PROXY` exclusions.
- **Manual:** enter an HTTP(S) proxy such as `http://127.0.0.1:7890`.
- **Direct:** ignore proxy settings.

Loopback model endpoints always connect directly. The page displays the detected proxy source
and sanitized addresses; requests may bypass it through `NO_PROXY`. PAC/WPAD scripts and SOCKS
are not supported. Manual proxy URLs must not contain credentials. Environment proxy credentials
are never returned to the page.

## Local configuration

Settings and the API key live in `.selfos-model.json` beside the scripts, outside the vault and
knowledge backups. This file and temporary save files are ignored by Git. It is a local plaintext
configuration file, not an encrypted credential store. The settings endpoint returns only whether
a key exists. A blank key field preserves it; the clear checkbox removes it. Switching provider
clears the previous provider key unless a new one is supplied.

Stop the current import before saving or testing another model. Switching models does not
automatically rebuild prior results. Model endpoint redirects are rejected to protect credentials.
