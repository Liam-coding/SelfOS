# Correcting your knowledge

Open a record in the knowledge browser to edit its description, delete it, or merge compatible records. Personal facts and preferences can merge only within the same relation and scope. Project merging uses the existing project alias workflow. The public screenshot demo is read-only.

Changes save directly with a backup. Recent knowledge changes shows the original descriptions, quotations and source links, plus Undo. If a later edit depends on an earlier merge, undo the dependent edit first. Undo replays the remaining actions against current generated knowledge; it does not replace newer imports with an old snapshot.

## What persists

The generated state and original source files remain unchanged. Actions live separately in `vault/.knowledge_corrections.json`; browser views, Markdown exports, chat and rebuild contexts apply this ledger. Manual content is labelled `user_correction`. Original quotations describe the previous generated claim and do not prove the edited content.

Deleting a sourced record suppresses its original source/quotation lineage within its knowledge category, including historical representations. Regenerating the same evidence with a new key or wording does not restore it. This can also hide another claim using that same quotation in the same category; inspect the preserved action history before undoing. Unsourced legacy records use their saved version instead.

Edits to personal facts or preferences remain effective for their relation and scope until undone. New supporting evidence remains visible as a conflict candidate. Project aliases carry these scopes to the canonical project. Project-purpose edits retain subsequent generated status and next steps; a different purpose backed by new sources appears as a candidate rather than replacing your edit.

Merging retains original records and source references. It resolves selected conflicting values; unselected or later conflicting evidence remains visible. Value-only API edits use the corrected value as their description rather than exporting an obsolete claim.

## Recovery and concurrent work

Saves use the vault lock, atomic journal and existing backups. Repeating an identical request ID returns its original action and backup. Stale versions are rejected. The page blocks corrections during an active import; a rebuild published later reapplies the current canonical ledger. A malformed ledger fails explicitly instead of silently ignoring corrections.

English and Chinese labels are available. Forms retain their input when switching language; controls support keyboard use.
