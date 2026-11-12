# SelfOS synthetic demonstration

These are the actual SelfOS dashboard templates and browser scripts, filled with completely fictional information. The English and Chinese datasets describe the same fictional person. All scores are demonstration values, not an assessment of a real person.

Open selfos-zh.html or selfos-en.html directly in a browser. No server is required. The read-only adapter supports category browsing, search, filters, source viewing and project timelines. It intercepts requests locally; it cannot scan original conversations, write to a real vault or call a model.

## Data for tests

- fixture.json: editable bilingual fixture, five project contexts and 16 retained records.
- en/vault and zh/vault: isolated generated knowledge snapshots, managed Markdown and score history.
- en/synthetic-conversations.json and zh/synthetic-conversations.json: normalized fictional source messages. These represent the internal message contract, not native Harness exports.
- build_demo.py: regenerate the real dashboard from the fixture and an explicitly selected SelfOS checkout.
- capture_demo.py: exercise all categories, original-source viewing and Overall navigation, then create screenshots. Uses Playwright Chromium, with an optional --browser executable path.

Regenerate from this directory:

    python -m pip install -e ../..
    python -m pip install playwright pillow
    python -m playwright install chromium
    python build_demo.py
    python capture_demo.py

The generator checks that every record has a source, category counts agree with the fixture, and all records refer to generated synthetic sources. No private vault is loaded. This fixture tests rendering, validation and source relationships; it does not measure a model's extraction accuracy.

## Screenshots

selfos-zh.png and selfos-en.png show the core dashboard and the five meaningful projects. The full-page and dimensions variants provide additional views. Text, layout and controls come from the existing SelfOS UI; the small demonstration label and local fixture adapter are the only additions.
