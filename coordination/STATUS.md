# EVA — STATUS (each agent edits only its own section)

Contract version: 0.1.0 · Last human merge: <time>

## FE
- Done:
- In progress:
- Blocked / needs:
- Next:

## BE
- Done:
- In progress:
- Blocked / needs:
- Next:

## SEC-1
- Done:
- In progress:
- Blocked / needs:
- Next:

## SEC-2
- Done: contracts package v0.1.0 (`contracts/models.py`), `CHANGES.md`, exported `contracts/openapi.json`, TypeScript types (`contracts/ts/`), `StubGuard` (`guard/eva_guard/stub.py`), `Guard` facade skeleton (`guard/eva_guard/api.py`), unit tests passing (15/15). Gate G0 complete.
- In progress: Task Policy Builder (`policy/`), templates, and Deterministic Gateway (`gateway/`).
- Blocked / needs: None.
- Next: Policy templates + LLM drafter client, gateway 11-rule engine, hash-chained audit table, approvals engine, state verifier, evaluation corpus v1.

## Gates
- [x] G0 contracts frozen + StubGuard (H0.75)
- [ ] G1 full loop on StubGuard; real scan + check behind facade (H3.5)
- [ ] CP-A injected-email scenario S1 end to end (H4)
- [ ] CP-B demo scenarios S1,S2,S4,S7,S12 (H7)
- [ ] CP-C metrics table produced (H9)
