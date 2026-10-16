# Request sec2-to-be-01
Status: OPEN
From: SEC-2 · To: BE · Date: 2026-10-16

## Need
1. **Stop reaching into guard internals in `agent/backend/tests/test_admin_scenarios.py`.** `admin_routes._active_config` and `_proposals` no longer exist: config, four-eyes proposals, the review queue, policies, approvals and the kill switch are now persisted in the guard SQLite DB (`GUARD_DB_PATH`, default `./guard.db`). In the `admin_proxy` fixture replace the `saved_cfg`/`_active_config`/`_proposals` lines with a single teardown call `guard_instance.reset_config_for_tests()` (available only when `APP_ENV` is eval/dev/test). I verified this patch in a scratch merge.
2. **Set `GUARD_DB_PATH` to a temp file in BE's test conftest** so tests do not share durable guard state (a repeated `task_id` now returns the stored policy; policies are immutable per task).
3. `build_task_policy` is idempotent per `task_id` (retry-safe) and an approval is only valid for its own task and only the task owner (`policy.user_id`) can resolve it.

## Why / what breaks without it
Without 1, `test_s13`/`test_s14` error on `AttributeError`. (Note: on `role/backend-ops` alone those two already fail with `KeyError: 'minimum_detector_posture'` from `GET /api/admin/config` in the S13 test; not caused by SEC-2.)

## Integration findings from a scratch merge (BE backend-ops + SEC-2 + SEC-1)
BE suite with `GMAIL_MODE=mock`: 131 pass / 4 fail (S13, S14 above; `test_run_scenario_full_passes[S10]` and `[S11]`). S10/S11 are detector false positives on the mock mailbox, see `sec2-to-sec1-02`.

## Answer (recipient fills in)
