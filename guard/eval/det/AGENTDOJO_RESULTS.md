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


## Workspace suite (email / calendar / drive) — full run

- Same setup (agentdojo 0.1.35, v1.2.1, `important_instructions`, `gemma4:31b-cloud`, EVA commit 7128476). **All 40 user tasks x all 14 injection tasks = 560 attack pairs + 40 no-attack runs**; one run per cell. The runs were interrupted twice and resumed with `--resume` (episodes already logged were reused).

| | no defense | EVA DET |
|---|---|---|
| Utility (no attack) | 33/40 (82.5%, 95% CI 68-91) | 25/40 (62.5%, 47-76) |
| Utility under attack | 467/560 (83.4%, 80-86) | 342/560 (61.1%, 57-65) |
| Attack success rate | 16/560 (2.9%, 2-5) | 17/560 (3.0%, 2-5) |

EVA scanned 1,924 tool results and sanitized **1,818 (94.5%)**; 0 held, 0 errors.

**Reading.** This model almost never follows the injection on workspace tasks (2.9% baseline), so there was little for the defense to stop; EVA did not change the attack success rate but cost about 21 points of utility. Cause (reproduced offline): tool outputs are YAML, and the T2 model scores bare lines like `- emma.johnson@bluesparrowtech.com` ~0.9 (it treats `com`/`org`/`net` as attack tokens), so participants and descriptions are stripped. On banking the same defense cut attack success from 59.7% to 29.2%. Together: the scanner helps when attacks work, but over-removes on structured, address-heavy tool output (KNOWN_LIMITS #10). No tuning was done on these suites; any fix made now means a re-run on workspace is no longer independent.
