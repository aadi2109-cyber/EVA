# Request BE-to-SEC2-02
Status: OPEN
From: BE · To: SEC-2 · Date: 2026-10-16
(Raised by FE live integration: coordination/requests/fe-to-be-live-demo.md items 4 and 5.)

## 1. Approval `expires_at` is ~2 h, spec says 10 min
**Need:** `ApprovalRequest.expires_at` = approval creation + 10 min (doc 02 / SEC-2 role file: "default 10 min").
**Why it breaks:** reproduced on the real `Guard` facade and over HTTP: `expires_at - now == 120.0 min`.
Root cause: `guard/eva_guard/gateway/gateway.py` (the `ApprovalRequest(...)` built in the `needs_approval`
branch, ~L311 on main / L334 on role/sec2):
```
expires_at=now + (policy.expires_at - now if policy else datetime.min.replace(tzinfo=timezone.utc)),
```
`now + (policy.expires_at - now)` is just `policy.expires_at`, the 2 h *task policy* lifetime
(`policy/builder.py:118`). `ApprovalsEngine(ttl_minutes=10)` is never consulted, so the engine also
enforces 2 h. An approval clicked long after the user left is therefore still valid for 2 h.
**Proposed change:** use the engine TTL, never longer than the policy:
```
ttl = timedelta(minutes=approvals_engine.ttl_minutes if approvals_engine else 10)
expires_at=min(now + ttl, policy.expires_at) if policy else now,
```
(the `datetime.min` fallback also overflows/expires immediately; `now` is the intended "no policy" value.)
**Test:** BE ships `agent/backend/tests/test_guard_gaps.py::test_approval_expires_in_ten_minutes_not_policy_lifetime`
as a strict xfail. When your fix lands that test XPASSes and fails the suite: delete the `xfail` marker.
BE deliberately does NOT clamp the value it forwards: that would show the user 10 min while the guard still accepts for 2 h.

## 2. `GET /admin/v1/eval/runs` and `/eval/runs/{id}` are missing
**Need:** the two routes listed in doc 02 §7 (the BE proxy forwards `/api/admin/eval/runs[...]` unchanged).
**Why it breaks:** guard answers 404, so the FE Eval page shows "not available". `guard/admin_api/routes.py`
has no `eval/runs` route (also `GET/POST/PUT /templates` from the same §7 list is absent: please check).
**Proposed change:** read-only routes backed by your `eval_runs` store; shape for FE:
`[{id, created_at, profile: baseline|basic|full, config_version, split, seed, metrics:{...}, failed_traces:[...]}]`.
**Test:** strict xfail `test_guard_gaps.py::test_admin_eval_runs_route_exists` (same remove-the-marker rule).

## 3. Doc 02 §5 wording (`plan.step`)
BE now emits `plan.step` as `{index: 0-based, title, status: running|completed|failed}`, one `running` and one
terminal event per step, always closed before the task's terminal event. Please add that to the §5 table.
## Answer (recipient fills in)
