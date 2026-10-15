"""
Tests for Core REST APIs: Tasks, Health, Files, and Approvals.
"""

import pytest
from app.config import settings


@pytest.mark.asyncio
async def test_health_endpoint(async_client, stub_guard_client):
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["backend"]["status"] == "ok"
    assert "guard" in data
    assert data["guard"]["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_tasks_crud_flow(async_client):
    # 1. Login
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_USER_EMAIL, "password": settings.SEED_USER_PASSWORD},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create task
    create_res = await async_client.post(
        "/api/tasks",
        json={"request": "Check pending tasks"},
        headers=headers,
    )
    assert create_res.status_code == 200
    task_id = create_res.json()["task_id"]

    # 3. List tasks
    list_res = await async_client.get("/api/tasks", headers=headers)
    assert list_res.status_code == 200
    task_summaries = list_res.json()
    assert any(t["id"] == task_id for t in task_summaries)

    # 4. Get task detail
    detail_res = await async_client.get(f"/api/tasks/{task_id}", headers=headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == task_id

    # 5. Cancel task
    cancel_res = await async_client.post(f"/api/tasks/{task_id}/cancel", headers=headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_files_api(async_client):
    login_res = await async_client.post(
        "/api/auth/login",
        json={"email": settings.SEED_USER_EMAIL, "password": settings.SEED_USER_PASSWORD},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = await async_client.get("/api/files", headers=headers)
    assert res.status_code == 200
    files = res.json()
    assert isinstance(files, list)
