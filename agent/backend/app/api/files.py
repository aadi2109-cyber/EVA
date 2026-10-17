"""
Files API for the frontend UI: read-only browsing plus a confined upload.

Uploads land only in the caller's own workspace (WORKSPACE_ROOT/<user_id>/). They are untrusted
content: the agent still reads them through files.read, whose output passes scan_tool_result.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.auth.deps import get_current_user
from app.config import settings
from app.db.models import User
from app.guard_client.factory import get_guard_client
from app.tools.files import MAX_FILE_BYTES, _get_sandbox_dir, _resolve_safe_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

MOCK_WORKSPACE = Path(__file__).resolve().parents[4] / "env" / "mock" / "workspace"
MAX_VIEW_BYTES = 512 * 1024
# Same cap as the agent's files.read, so every uploaded file can be viewed and read back.
MAX_UPLOAD_BYTES = MAX_FILE_BYTES
MAX_WORKSPACE_BYTES = 25 * 1024 * 1024  # per-user quota so uploads cannot fill the disk
_CHUNK = 64 * 1024


def _validate_upload_name(name: str | None) -> str:
    """A plain file name only: no separators, no dot-names, no control characters."""
    if (
        not name
        or len(name) > 255
        or name in (".", "..")
        or name.startswith(".")
        or name != Path(name.replace("\\", "/")).name
        or any(c in name for c in "/\\")
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name")
    return name


def _workspace_usage(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


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


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    current_user: Annotated[User, Depends(get_current_user)],
    path: str = Query(default="", description="Relative workspace directory to upload into"),
) -> dict[str, Any]:
    name = _validate_upload_name(file.filename)
    try:
        target_dir = _resolve_safe_path(current_user.id, path)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not target_dir.is_dir():
        # Never create folders implicitly: that could shadow the read-only mock folders.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found in your workspace")

    sandbox = _get_sandbox_dir(current_user.id)
    dest = target_dir / name

    # Read at most MAX_UPLOAD_BYTES + 1 so an oversize file is rejected without buffering it all.
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {MAX_UPLOAD_BYTES // 1024} KB upload limit",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    if _workspace_usage(sandbox) + size > MAX_WORKSPACE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Workspace quota exceeded")

    # O_EXCL: never overwrite, and never follow a pre-existing symlink at the destination.
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{name} already exists")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    rel = dest.relative_to(sandbox).as_posix()
    digest = hashlib.sha256(data).hexdigest()

    # Tamper-evident audit entry in the guard's hash chain. Fail closed like the rest of the system:
    # if the event cannot be recorded, the upload is rolled back.
    try:
        await get_guard_client().record_event(
            task_id=f"upload:{current_user.id}",
            event_type="files.uploaded",
            actor=f"user:{current_user.id}",
            payload={"path": rel, "size": size, "sha256": digest},
        )
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.error("Upload rolled back: audit write failed: %s", e)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Audit log unavailable; upload not saved")

    logger.info("file.uploaded user=%s path=%s size=%d sha256=%s", current_user.id, rel, size, digest)
    return {"path": rel, "size": size}
