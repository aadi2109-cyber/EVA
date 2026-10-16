# EVA — Branch Progress Report

Date: 2026-10-16

Percentages are estimates, not measured values. Each branch was scored against its role's scope in `docs/01-coordination-and-schedule.md`, using its `coordination/STATUS.md`, its commits and its diff against `main`. No test suite was run to produce this report.

`main` and `claude/hopeful-keller-rgf1u7` point at the same commit (`babbb2a`). `main` already contains the merged `role/backend` work from PRs #1 and #2.

## Summary

| Branch | Role | Est. progress | Ahead of `main` |
|---|---|---|---|
| `role/backend` | Backend (BE) | ~85% | 2 commits |
| `role/backend-ops` | Backend hardening (split from BE) | ~35% (as a standalone task) | 2 commits |
| `role/frontend` | Frontend (FE) | ~65% | 1 commit |
| `role/sec1` | Detection (SEC-1) | ~65% | 5 commits |
| `role/sec2` | Guard authority (SEC-2) | ~85% | 10 commits |

Overall: ~70%.

## `role/backend` (~85%)

**Done**
- The orchestrator, tool registry, providers, SSE and the `env/` fixtures are delivered. The CP-A and CP-B gates are met.
- The latest commit adds SSRF DNS pinning, `web.search` providers and Ollama failure handling.
- STATUS claims 205 of 205 backend tests passing.

**Missing**
- Real Gmail/OAuth and the Docker build have only been tested against mocks.
- The `web.search` and Ollama paths have never run against live services.
- Scenario S9 depends on SEC-1's detector.
- CP-C robustness is still in progress.

## `role/backend-ops` (~35%)

**Done**
- Two commits: hardened backend HTTP guard and recovery paths, and a declared async SQLite dependency.
- There is no STATUS entry for this branch.

**Missing**
- The work overlaps `role/backend`, so it has no scope of its own to score against. The percentage only reflects that it is a narrow slice of hardening.

## `role/frontend` (~65%)

**Done**
- Every page and component is built: the live trace panel, the approval modal, connectors, files, history and admin.
- The API client and SSE client are typed to contract v0.
- The mocked scenarios S1, S2, S4 and S7 are done.

**Missing**
- STATUS says the install and build validation is still in progress, so it is unconfirmed that the app compiles.
- It has never been pointed at the real backend (CP-A).
- The degraded banners, accessibility pass and demo polish haven't started.
- Its STATUS still lists CP-A integration as next, although the backend reached CP-A on `main`.

## `role/sec1` (~65%)

**Done**
- The detection pipeline is built: T1 rules, provenance, sentence splitter, sanitizer, T3 adapter with timeout, and health telemetry.
- The Guard facade supports both sync and async use.
- T2 training scripts and ONNX exports are added.
- 66 tests pass, according to STATUS.

**Missing**
- The T2 model is still unproven. SEC-2's measurement through the Guard facade gives test recall of about 21%, which is low.
- Threshold calibration is not done.
- LAYA is not validated.
- The final known-limits report isn't written.

## `role/sec2` (~85%)

**Done**
- The contracts, policy builder, gateway, approvals, audit chain, state verifier, admin API and service are all delivered.
- The S1–S14 runner shows Full mode at 14 of 14 expectations with 0 unauthorized side effects.
- The 10 degradation drills all fail closed.
- It has already merged `role/sec1`, and 72 tests pass.

**Missing**
- The ALIGN check isn't validated against LAYA.
- The eval report and known-limits write-up are not finished.
- Its STATUS "In progress" text is stale.

## Conclusions

- Only the backend work is merged to `main`. Frontend, sec1, sec2 and backend-ops are all unmerged.
- The biggest risk is the detector's low recall on the test split.
- Next step: merge `role/sec1` and `role/sec2` into `main`, then run CP-C, the metrics table.
