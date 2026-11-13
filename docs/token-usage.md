# Knowledge import token usage

Import settings and the running progress window display measured requests, failed attempts, elapsed time, input/output/total tokens, and cache read/write tokens. Counters refresh during imports and recovery. Viewing usage and saving the allowance never call a model or scan source conversations.

Token counts come from provider responses. Missing, malformed, failed, or interrupted responses retain an unknown-usage count; recorded totals are partial whenever this count is nonzero. Anthropic input totals include reported cache reads and cache creation. OpenAI prompt totals already include cached input, so cached reads are shown as a subset and are not added again. No prices or monetary costs are calculated.

The request allowance defaults to 100 per checkpoint. Actual attempts, including retries and review calls, share a durable journal across workers and restarts. Exhaustion preserves saved work; raising the allowance explicitly permits resumption. Existing onboarding sample allowances remain authoritative. Journals contain metadata, not prompts or API keys.

Legacy optional pricing fields are ignored and removed on the next allowance save. New pricing fields are rejected. Workload predictions are deferred to a follow-up to #22; this feature only measures actual usage.
