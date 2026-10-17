# ADR 0008: Vendor selection and private credential configuration

- **Status:** accepted (2026-10-17)
- **Decides:** which vendor/model the seam talks to, and how its credential is
  configured privately
- **Related:** issue #29 (B items 2 and 4), ADR 0002 (contract authority),
  ADR 0003 (approval and execution)

## Decision

1. **Text and vision vendor: DeepSeek `deepseek-chat`.** It is the vendor the
   operator holds a key for, it answers the extraction contract shape, and a
   real probe showed the endpoint processes image inputs for this account
   (a solid green / red 64x64 PNG returned "Green" / "Red" at 202 prompt tokens
   each). Vision is nevertheless still gated by
   `GIGMATE_MEDIA_VISION_VENDORS=deepseek`: the probe is an account-routing
   observation, not a vendor capability guarantee.
2. **Audio has no vendor.** ASR needs its own OpenAI-compatible
   `/v1/audio/transcriptions` endpoint. DeepSeek is refused explicitly for
   audio, because posting the chat key to a default ASR endpoint would be a
   silent credential misuse. Until an audio vendor is chosen, `asr` is refused
   with `MEDIA_AUDIO_VENDOR_REQUIRED`.
3. **Credentials are configured as files, not values.**
   `GIGMATE_LLM_API_KEY_FILE` / `GIGMATE_MEDIA_API_KEY_FILE` (or an equivalent
   secret mount) take precedence over the value variables; a file that is named
   but unreadable is a hard `SecretUnreadable` failure instead of degrading to
   "unconfigured". Values remain supported for local work.
4. **Enabling is a checklist, never a single switch.** Live gate, budget,
   prices, token caps, time basis, media seam, modalities, vision vendors and
   the ASR vendor are independent gates; `scripts/check_model_config.py`
   reports their presence without printing a value.

## Rationale

Issue #29 puts vendor selection and private configuration on the maintainer,
while the code must never make the decision silently. Keeping the credential in
a file means it does not appear in `docker inspect`, process listings, shell
history or a container image layer. Refusing audio rather than reusing the chat
key keeps "we have a key" from turning into "we use that key for everything".
Not choosing an audio vendor is recorded as an open decision rather than
covered by a default.

## Consequences

- A deployment is only live when every gate is configured; the seam stays
  closed otherwise, so an incomplete configuration cannot make unexpected
  calls or spend money.
- Real price, budget and token caps must be entered by the maintainer and
  re-checked when the vendor changes its price list — the configuration is not
  a substitute for that review, and `check_model_config.py` states so.
- **Still open:** no audio vendor is procured, and no production credential has
  been deployed. Both are operator actions, not code changes, and issue #29
  items 2 and 4 stay unchecked until they happen.

## Enabling checklist

1. `umask 077 && printf '%s' "$KEY" > /run/secrets/deepseek`
2. `GIGMATE_LLM_API_KEY_FILE=/run/secrets/deepseek`
3. `GIGMATE_EXTRACTION_PROVIDER=reviewed_llm`,
   `GIGMATE_LLM_PROVIDER=deepseek`, `GIGMATE_LLM_MODEL=deepseek-chat`
4. `GIGMATE_LLM_COST_INPUT_USD_PER_1K` / `GIGMATE_LLM_COST_OUTPUT_USD_PER_1K`
   from the vendor's published price list (record the date you checked it)
5. `GIGMATE_LLM_COST_BUDGET_USD`, `GIGMATE_LLM_MAX_INPUT_TOKENS`,
   `GIGMATE_LLM_MAX_OUTPUT_TOKENS` (per-call bounds; daily model call/token
   budgets and a model account allowlist are not implemented by this batch)
6. `GIGMATE_WORKSPACE_TIMEZONE` (relative dates are resolved against it)
7. `GIGMATE_LLM_LIVE=1` and `GIGMATE_LLM_ALLOW_LIVE_ORIGIN=1`
8. Media only if needed: `GIGMATE_MEDIA_ENABLED=1`,
   `GIGMATE_MEDIA_MODALITIES=ocr,pdf,text`,
   `GIGMATE_MEDIA_VISION_VENDORS=deepseek`
9. `python scripts/check_model_config.py` — checks the selected reviewed runtime,
   gates, operator prices, credential presence and timezone, without making a
   vendor request or printing a key. Exit 0 means text configuration is complete;
   legacy `llm`, deterministic/disabled providers and incomplete configurations
   exit 1. Media is reported separately and does not become authorised through
   this check. This is configuration inspection, not vendor acceptance.
