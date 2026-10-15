# EVA — Development Instruction Pack

EVA is a tool-using AI agent (Gmail, files, web, messages, tool outputs, multi-step tasks) protected by a separate, modular security system. The agent and the security system are built **in parallel by four agents in one working day**, against a frozen contract.

This folder is everything those agents need. Copy it into the repo as `docs/`.

## Read order (every agent)

1. `00-overview-and-decisions.md` — what we are building, confirmed decisions, security principles
2. `01-coordination-and-schedule.md` — repo layout, ownership, one-day schedule, hand-offs
3. `02-contracts-v0.md` — the API/schema contract between agent and security system (the only thing the two sides share)
4. `03-environment-and-setup.md` — env vars, Ollama cloud, Gmail OAuth, laptop constraints, mock environment
5. **Your role file** in `roles/`
6. `04-evaluation-and-acceptance.md` — scenarios, metrics, demo script, honest-claims rules

## Roles and starting prompts

| Agent | Role file | Paste-ready starting prompt |
|---|---|---|
| FE — Frontend | `roles/frontend.md` | `prompts/frontend.md` (asks the human for the UI reference link first) |
| BE — Backend | `roles/backend.md` | `prompts/backend.md` |
| SEC-1 — Content side (detection) | `roles/security-1-content.md` | `prompts/security-1.md` |
| SEC-2 — Authority side (policy, gateway, audit, eval) | `roles/security-2-authority.md` | `prompts/security-2.md` |

## Humans must do these before/at hour 0 (agents cannot)

- [ ] Create the repo and give each agent its own working branch/worktree (`01-coordination-and-schedule.md` §2)
- [ ] Provide the Ollama cloud API key and model name (`03-environment-and-setup.md` §2)
- [ ] Create the Google Cloud OAuth client + test users for the dedicated Gmail account (`03-environment-and-setup.md` §3). Until done, BE runs with `GMAIL_MODE=mock`
- [ ] Give the **UI reference link to the FE agent in its own chat** (FE will ask for it)
- [ ] Relay cross-agent requests (agents are in separate chats; they communicate through files in `coordination/`, you move the branch merges at checkpoints)

## Templates

`templates/STATUS.md` → copy to `coordination/STATUS.md`. `templates/request.md` → format for `coordination/requests/`.

## Rules that apply to everyone

- The security system never imports from the agent and vice versa. Shared surface = `contracts/` only.
- Any guard error, timeout or unreachable service is treated by the agent as **DENY / held**. Never fail open.
- Detectors and ALIGN are advisory. The deterministic gateway is the only authority.
- Security tests and evals run on the **mock** mailbox/files/web only — never on real Gmail.
- No secrets in prompts, logs, or the repo. `.env` is git-ignored.
- Claims must be measured and reported with test counts, never "immune" or "unbreakable".
