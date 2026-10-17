import tempfile

from fastapi.testclient import TestClient

import admin_api.routes as routes
import service.main as svc
from eva_guard.api import Guard
from eval.store import EvalStore

H = {"Authorization": f"Bearer {svc.SERVICE_TOKEN}"}


def test_store_roundtrip_and_ordering():
    st = EvalStore(f"{tempfile.mkdtemp()}/e.db")
    a = st.save_run("drills", {"passed": 9, "total": 10}, n=10, failures=[{"id": "D3"}], config={"env": "mock"}, seed=7)
    b = st.save_run("drills", {"passed": 10, "total": 10}, n=10)
    runs = st.list_runs("drills")
    assert [r["id"] for r in runs] == [b, a]
    full = st.get_run(a)
    assert full["failures"] == [{"id": "D3"}] and full["seed"] == 7 and full["versions"]["contract"] == "0.1.0" and full["hardware"]
    assert st.get_run("nope") is None


def test_admin_eval_endpoints_and_comparison_table():
    g = Guard(db_url=f"sqlite:///{tempfile.mkdtemp()}/g.db")
    old = getattr(routes, "_guard_singleton", None)
    routes._guard_singleton = g
    try:
        st = EvalStore(g._audit.db_path)
        prof = {p: {"unauthorized_side_effects": n, "task_under_attack_completion": "7/7", "clean_task_completion": "3/3", "expectations_met": "n/a"}
                for p, n in (("off", 9), ("basic", 2), ("full", 0))}
        rid = st.save_run("scenarios", {"profiles": prof}, n=42)
        c = TestClient(svc.app, raise_server_exceptions=False)
        assert c.get("/admin/v1/eval/runs").status_code == 401
        runs = c.get("/admin/v1/eval/runs", headers=H).json()
        assert runs and runs[0]["id"] == rid
        assert c.get(f"/admin/v1/eval/runs/{rid}", headers=H).json()["n"] == 42
        assert c.get("/admin/v1/eval/runs/missing", headers=H).status_code == 404
        assert c.get("/admin/v1/eval/runs?kind=bogus", headers=H).status_code == 422
        tbl = c.get("/admin/v1/eval/summary", headers=H).json()["comparison_table"]
        row = next(r for r in tbl if r["metric"] == "unauthorized_side_effects")
        assert (row["baseline"], row["basic"], row["full"]) == (9, 2, 0)
    finally:
        routes._guard_singleton = old if old is not None else routes._guard_singleton
