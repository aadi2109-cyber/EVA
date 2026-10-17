# AgentDojo live run — EVA DET defense (content scanner only)

- Date 2026-10-17 · agentdojo 0.1.35 · suite **banking** (v1.2.1) · attack `important_instructions` · EVA commit 7128476
- Agent LLM: `gemma4:31b-cloud` via Ollama cloud (not in AgentDojo's model list, so attacks address it as "Local model")
- Scope: user tasks 0-7 x all 9 injection tasks (N = 72 attack pairs; 8 no-attack runs). **One run per cell, temperature default; no repeats.**
- Defense `eva` = every tool result scanned by `Guard.scan_tool_result` (T1 + T2; T3 not installed) before the LLM sees it. SEC-2 gateway/approvals are **not** in the loop.

| | no defense | EVA DET |
|---|---|---|
| Utility (no attack) | 8/8 | 7/8 |
| Utility under attack | 63/72 (87.5%) | 55/72 (76.4%) |
| Attack success rate (lower is better) | 43/72 (59.7%, 95% CI 48-70) | 21/72 (29.2%, 95% CI 20-40) |

EVA scanned 206 tool results, sanitized 80, held 0, 0 scanner errors.

Caveats: one suite, 8 of 16 user tasks, one model, one seed; the 72 pairs share 8 user tasks so they are not independent (true intervals are wider). Utility fell by about 11 points under attack, consistent with the known over-removal of benign short sentences (KNOWN_LIMITS #9). Nothing was tuned on AgentDojo. Raw logs: `eval/det/agentdojo_runs/` (gitignored).
