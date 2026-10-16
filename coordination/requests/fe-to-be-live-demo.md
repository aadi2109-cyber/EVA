# FE -> BE requests (from live integration, CP-A)

1. **Demo model switch.** Live tasks use OllamaProvider only; without `OLLAMA_API_KEY` every task ends with `403 Forbidden`. Please add an env switch (e.g. `MODEL_PROVIDER=scripted`) that picks a ScriptedProvider keyed on the request text so S1/S2/S4/S7 can be demoed through the UI. FE verified against a test-only launcher that does this.
2. **`tool.output` payload.** Contract §5 says "sanitized result"; BE sends `sanitized_output` (string). FE now reads `sanitized_output ?? result`. Please confirm `sanitized_output` is the contract field and update doc 02.
3. **`plan.step` status.** BE only emits `status: "running"` and never completes a step. FE infers completion (next step starts / task terminal). Emit `completed` explicitly if possible. Indexes are 1-based on BE.
4. **Approval expiry.** `ApprovalRequest.expires_at` is ~2h out in the live run; spec says 10 minutes.
5. **`/api/admin/eval/runs`** returns 404 (guard has no such route); FE shows "not available".
6. **Health metrics** `p50_ms`/`p95_ms` come from guard `metrics`; FE shows them when present.
