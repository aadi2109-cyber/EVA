"""
Files browsing API for frontend UI (read-only workspace exploration).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import get_current_user
from app.config import settings
from app.db.models import User
from app.tools.files import _resolve_safe_path

router = APIRouter(prefix="/api/files", tags=["files"])

MOCK_WORKSPACE = Path(__file__).resolve().parents[4] / "env" / "mock" / "workspace"
MAX_VIEW_BYTES = 512 * 1024


def _mock_path(rel: str) -> Path | None:
    """Resolve rel inside the read-only mock workspace; None if it escapes or does not exist."""
    root = MOCK_WORKSPACE.resolve()
    cand = (root / rel.lstrip("/\\")).resolve()
    try:
        cand.relative_to(root)
    except ValueError:
        return None
    return cand if cand.exists() else None


@router.get("")
async def list_user_files(
    current_user: Annotated[User, Depends(get_current_user)],
    path: str = Query(default="", description="Relative workspace path"),
) -> list[dict[str, Any]]:
    try:
        target = _resolve_safe_path(current_user.id, path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not target.exists() or not target.is_dir():
        # Check mock workspace if user folder is empty
        mock_dir = _mock_path(path)
        if mock_dir is not None and mock_dir.is_dir():
            return [
                {"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
                for p in sorted(mock_dir.iterdir())
            ]
        return []

    return [
        {"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
        for p in target.iterdir()
    ]


@router.get("/content")
async def get_file_content(
    current_user: Annotated[User, Depends(get_current_user)],
    path: str = Query(..., description="Relative file path"),
) -> dict[str, str]:
    try:
        target = _resolve_safe_path(current_user.id, path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not target.exists() or not target.is_file():
        mock_file = _mock_path(path)
        if mock_file is not None and mock_file.is_file():
            target = mock_file
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if target.stat().st_size > MAX_VIEW_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large to display")
    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": content}
