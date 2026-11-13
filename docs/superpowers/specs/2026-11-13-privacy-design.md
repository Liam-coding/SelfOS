# Privacy and portable migration

Issue #13: source rules apply before compacting messages and immediately before every model attempt. Reuse source selection, extend exclusions to project and upload paths. Previously imported knowledge remains locally inspectable; records touching excluded sources are withheld from model context. Unsourced legacy context is withheld while exclusions are active. Changes during imports abort publication.

Export a versioned JSON envelope of canonical state, corrections, source rules, knowledge policy and allowlisted model settings. Credentials, originals, diagnostics and backups are omitted by default. Explicit controls permit contained uploaded originals and backups. Import requires an empty knowledge destination, validates entries before writes and reports all source links. Included uploaded paths are rebased; historical provenance stays intact. No model calls.

Settings uses native HTML/JavaScript and English/Chinese catalogs. Copy explains model input, provider endpoint, local storage, limitations of redaction, retained knowledge and export sensitivity.
