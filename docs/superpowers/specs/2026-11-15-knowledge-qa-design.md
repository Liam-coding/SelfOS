# Source-cited knowledge question answering (#18)

The existing chat assembles broad vault context and returns a reply string without record-bound citations. Default knowledge questions should instead retrieve relevant retained knowledge, answer from that projection and let the user inspect its original evidence. This builds on #16/PR #84; product-wide simplification remains #83.

## Decisions

Use deterministic retrieval over existing canonical records, not another conversation-extraction or query-model pass. Apply persistent corrections, preference lifecycle rules and current source/privacy filtering before selecting anything for the model. Reuse the library's stable record IDs, source scopes and original-source viewer. Broad companion chat remains explicitly selectable for existing score/advice workflows; knowledge mode is the ordinary question-input default. Programmatic legacy chat methods retain compatibility.

Model-generated summary text is labeled model interpretation, never independently verified fact. Supporting record cards display imported evidence kind, manual correction, current/history status, conflict and source scope from server metadata. The model selects admitted record IDs; it does not create URLs, filesystem paths, citation provenance or original quotation text. Literal evidence displayed alongside the summary comes from retained records.

Attribution checks prove reference membership and preserve evidence provenance; they do not prove semantic entailment of arbitrary generated prose. The interface must not claim they do. Representative/adversarial fixtures and a strict insufficient-evidence path test answer quality.

## Retrieval and bounds

- Accept one latest question, at most 2,000 characters; an optional existing project-context ID at most 100 characters; English/Chinese locale. Do not send earlier assistant replies or the whole chat/vault as knowledge context.
- Reduce English question stopwords and Chinese question scaffolding; rank strong canonical fields with deterministic lexical scoring. Recognized overview questions can retrieve current projects, preferences, facts or lessons without a named keyword. Unsupported specific questions do not fall back to unrelated records.
- Current-only by default. Explicit historical/decision questions can retrieve clearly marked historical records. Do not label completed/unknown projects as active work, expired preferences as current, or manually corrected text as an original quotation.
- Select at most 8 relevant records, 12,000 record-text characters and 24 evidence references. A record with many sources uses explicitly labeled representative source/context references; bounded source display does not claim complete evidence coverage.
- Missing, excluded or malformed knowledge is an explicit state. No selected evidence means no model call and no invented personal facts or decisions.

## Answer and privacy boundary

- One structured answer call through the existing configured Anthropic/OpenAI-compatible provider/network adapter, with at most one repair call for malformed attribution/output. The request allowance is 2, including repair; record token usage without pricing.
- Model output contains answered/insufficient-evidence status, a bounded summary, admitted record IDs and explicitly labeled inferences with admitted basis IDs. For answered status, require nonempty known references. Reject foreign IDs, malformed types and excessive output; never expose raw invalid model output as a sourced answer.
- Derive citation IDs, source lists, correction flags, current/history flags and source-scope labels on the server. Returning insufficient evidence uses localized deterministic copy rather than arbitrary unsupported model prose.
- Capture source-policy and canonical/correction revisions. Revalidate before requests and before returning an answer; changed knowledge/privacy yields an explicit refresh/retry state. Validate an answer's record revision before navigating a citation, so old answers cannot silently point to a different corrected record.
- Cancellation stops the UI wait and prevents further local follow-up/repair. A request already sent to a provider may still finish within its bounded timeout; do not imply cancellation refunds it. No conversation files are modified, scanned in bulk or newly extracted.

## Browser workflow

Extend the private chat owner with knowledge/conversation selection, optional project scope, cancel/loading/failure states and source-cited result rendering. Keep one owner for chat controls and messages; extract private pure helpers/resources if necessary. Preserve drafts and cited-message metadata across remount. Abort/dismiss stale results, coalesce duplicate sends and use text-safe DOM rendering.

Citation navigation reuses the knowledge detail/original-source surfaces. English remains the default and all new visible strings have Chinese translations. Keyboard, responsive desktop/mobile and cached refresh retain one set of controls/listeners. #83 will simplify the complete import-to-question journey after this works.

## Verification

Synthetic retained records cover current projects, decision reasons, preferences/lessons, explicit history, correction, conflict, missing evidence, source exclusion, stale revisions and injected evidence instructions. Actual browser checks cover both locales, project scope, cancel/remount and citation navigation. Loopback providers test both API interfaces, repair bounds and token accounting. No paid model calls, personal conversation scans, new dependency or price calculations. Existing general-chat/score behavior and installed-wheel refresh/resource checks remain covered.
