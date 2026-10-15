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
        mock_ws = Path("env/mock/workspace")
        if mock_ws.exists():
            return [
                {"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
                for p in mock_ws.iterdir()
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
        mock_file = Path("env/mock/workspace") / path.lstrip("/\\")
        if mock_file.exists() and mock_file.is_file():
            target = mock_file
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": content}
