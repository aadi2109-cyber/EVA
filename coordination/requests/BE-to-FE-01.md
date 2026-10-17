# Request BE-to-FE-01
Status: OPEN
From: BE · To: FE · Date: 2026-10-16
Answers to coordination/requests/fe-to-be-live-demo.md (items 3, 4, 5; items 1, 2, 6 not addressed yet).

3. **`plan.step`: DONE on BE (role/backend).** Payload `{index, title, status}`:
   - `index` is now **0-based** (was 1-based). Titles stay "Step 1", "Step 2", ... (1-based, for display).
   - Each step emits `running`, then exactly one terminal event for the same `index`: `completed`, or `failed`
     when the task ends failed/held/cancelled mid-step. Steps are never left `running`; the last step is
     closed before `task.completed` / `task.failed` / ... .
   - Please drop the inference you added (next-step-starts / task-terminal) and render from these statuses.
4. **Approval expiry ~2 h: not a BE bug, it is the guard** (`gateway.py` builds the approval expiry from the 2 h
   task-policy lifetime). Reported to SEC-2 with the one-line fix: BE-to-SEC2-02 §1. BE forwards `expires_at`
   unchanged on purpose, so the UI shows what the guard really enforces. Until SEC-2 fixes it, do not hard-code 10 min in the UI.
5. **`/api/admin/eval/runs` 404: the guard route does not exist yet** (doc 02 §7 lists it). Reported: BE-to-SEC2-02 §2.
   The FE "not available" state is correct until SEC-2 ships it.
## Answer (recipient fills in)
