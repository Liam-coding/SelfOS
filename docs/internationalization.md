# Internationalization

SelfOS defaults to English and includes Simplified Chinese. A shared catalog supplies server-rendered text and browser translations. Language selection is stored locally as selfos-lang. Legacy zh preferences resolve to zh-CN through locale metadata; unsupported preferences fall back to English.

## Catalogs and adding a language

Locale resources live in src/selfos/resources/locales/<locale>/. Each directory contains meta.json and message namespaces such as ui.json, auth.json, search.json, timeline.json and import.json. Keys inside a namespace are flat; the runtime prefixes them with the filename, for example search.found.

Add a directory with metadata and translated namespace JSON files. No feature-specific language branch is needed. Metadata declares:

- name: the language selector label.
- tag: the Intl date and number formatting locale.
- document_tag: the HTML language tag. Existing Simplified Chinese uses zh for compatibility with older saved dashboards.
- aliases: additional accepted persisted preferences.

For example, meta.json for an additional English locale can contain:

    {"name":"English (UK)","tag":"en-GB","document_tag":"en-GB","aliases":[]}

English defines the supported keys and parameter contract. A translation may omit a key and use the English fallback. Unknown extra keys, invalid metadata, duplicate aliases and inconsistent parameter names fail catalog validation. The validator reports missing translations separately so contributors can track coverage.

    python -c "from selfos.web.i18n import catalogs, validate_catalogs; print(validate_catalogs(catalogs())['missing'])"

## Writing UI messages

Keep user-visible messages in catalogs. Templates use data-i18n for text and data-i18n-placeholder, data-i18n-title or data-i18n-aria-label for attributes. Initial template text should be English. data-i18n-params contains escaped JSON parameters.

Dynamic UI uses window.selfosI18n.bindText(element, key, params). Bindings retain the key and parameters, so language changes update pending, success and error states without repeating the operation. Pass a parameter factory when parameters themselves contain translated labels or formatted dates. Plain t(key, params) is useful when producing a message at the time of a user action.

Use named placeholders such as {count}, with identical names in each locale. Numeric parameters use Intl number formatting. date(value) accepts explicit date-only values and timestamps with time zones, rejects invalid calendar dates and treats ambiguous legacy dates as unknown. Date-only values cannot acquire a time of day or change calendar day because of the viewer's time zone.

Translate labels around user records, filenames, source quotations and model replies; keep their actual content literal. Use textContent and safe attribute rendering. Never insert translation parameters or user filenames as HTML.

## Preserving state

A language event must not reload settings, rebuild list nodes, reset pagination, clear unsaved inputs, restart a source request or change a running import. Bind text to existing nodes. Keep API requests attached to the initiating user action or existing recovery loop.

Backend/provider diagnostics remain available in original import logs. UI errors use localized messages, and authentication retains HTTP status and error codes for session handling.

Authenticated dashboard reads refresh packaged components and scripts without writing the cached dashboard, scanning conversations or calling models. Older bilingual attributes have a central compatibility adapter. New maintained templates must use catalog keys.

## Verification

Catalog and JavaScript tests cover fallback, aliases, safe parameter interpolation, missing keys, numeric/date formats and state preservation during language changes. Browser regressions use temporary servers, synthetic sources and scripted import/model events.

    python -m pytest tests/test_i18n_catalogs.py tests/test_i18n_runtime.py tests/test_i18n_browser.py tests/test_i18n_cached_dashboard.py

Before publishing a change, run the complete test suite, inspect actual desktop/mobile pages and verify the built wheel contains all locale resources. The original frontend byte snapshot remains historical evidence for the resource refactor; active checks preserve styling and validate current keyed UI instead of requiring intentional language changes to match old bytes.
