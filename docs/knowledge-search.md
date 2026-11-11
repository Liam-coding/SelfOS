# Global knowledge search

The knowledge browser starts in All knowledge and searches published projects,
personal facts, preferences, reusable experience and history. Search uses the
existing canonical projection; it does not scan original conversations, send
content to a model or build a second knowledge store.

Queries contain at most 20 whitespace-separated terms and 500 characters. Every
casefolded term must match visible, redacted content in a record. Exact/phrase
title matches receive the strongest weight, followed by summary, decisions,
blockers, next steps and saved quoted evidence. Project context and domain have
lower weight. Results use deterministic date/record-ID tie breaks; an empty query
browses by recorded date. Matching excerpts are bounded to 260 characters and
highlights are Unicode character ranges rendered as text nodes.

Project context filters match a direct project association or projects referenced
by supporting sources. They do not assert that a personal preference applies only
to that project. Source filters use registered provider/type metadata. Date
ranges are inclusive calendar dates in YYYY-MM-DD form. Undated legacy history
stays undated and does not match date filters. Overall canonical counts remain
separate from category match counts for the current query and other filters.

Results expose their category, attribution, matched field and project context.
Details distinguish saved quotations from broader session/project context and
model-derived summaries. Missing source metadata is explicitly counted rather
than silently replacing it with unrelated sources. Original conversation reads
still require a known source ID, permitted local conversation folder and matching
message identity. Source errors distinguish missing/moved originals, changed
content, unsupported formats and denied locations.

Registered document evidence is supported ahead of the upload producer in #11.
It uses source=uploaded_file and a path under vault/.knowledge_uploads/originals
(relative vault paths are recommended for portability), content_sha256 and an
optional original_filename. Original bytes must match SHA-256 before reading.
The initial original viewer accepts UTF-8 TXT, MD, JSON and JSONL up to 20 MiB;
binary formats need future extraction adapters and return an explicit limitation.
Originals remain excluded from Git. Reads are redacted and paginated, at most
32,000 characters per request; the UI requests 24,000. These are evidence-reading
adapters, not an upload or classification workflow, and never promote a document
or AI-generated description into verified personal facts.

GET /__knowledge__ accepts category, query, project, source, date_from, date_to,
offset and limit. Project filter IDs are opaque tokens returned in filters.projects.
GET /__knowledge_source__ accepts a known id plus offset/limit and returns
next_offset for additional original text. Both remain authenticated and reject
cross-site reads. Existing generated dashboards refresh their search component
when served without rewriting dashboard.html or importing conversations again.
