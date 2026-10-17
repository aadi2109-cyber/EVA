"""
Files API for the frontend UI: browse + read the workspace, and upload text files into it.

Uploads are untrusted input: strict file-name rules, text-only, size/quota caps, atomic no-overwrite
create, written only inside the caller's own sandbox, and every attempt is audit-logged. Reading an
uploaded file by the agent still goes through files.read -> guard.scan_tool_result, so an upload
cannot bypass the guard.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.auth.deps import get_current_user
from app.config import settings
from app.db.database import get_db_session
from app.db.models import FileAuditEvent, User
from app.tools.files import MAX_FILE_BYTES, _get_sandbox_dir, _resolve_safe_path

logger = logging.getLogger("eva.files")

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


# ------------------------------------------------------------------------------ upload
MAX_UPLOAD_BYTES = MAX_FILE_BYTES            # an upload must stay readable by files.read (512 KB)
MAX_REQUEST_SLACK = 16 * 1024                # multipart framing overhead allowed above the file limit
WORKSPACE_QUOTA_BYTES = 20 * 1024 * 1024
WORKSPACE_QUOTA_FILES = 500
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".yaml", ".yml", ".xml"}
_NAME_OK = re.compile(r"^[\w\-. ()\[\]]+$")
_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _check_filename(raw: str | None) -> str:
    """Return a safe file name or raise HTTPException (400 bad name / 415 type not allowed)."""
    name = raw or ""
    if not name or len(name) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file name")
    if "/" in name or "\\" in name or ".." in name or "\x00" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File name must not contain path separators, '..' or control characters")
    if name.startswith(".") or name.endswith((".", " ")) or not _NAME_OK.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file name (no leading dot, trailing dot/space or special characters)")
    stem, ext = os.path.splitext(name)
    if stem.lower() in _WIN_RESERVED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reserved file name")
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Only text files are accepted ({', '.join(sorted(ALLOWED_EXTENSIONS))})")
    return name


def _workspace_usage(sandbox: Path) -> tuple[int, int]:
    total = count = 0
    for p in sandbox.rglob("*"):
        if p.is_file() and not p.is_symlink():
            count += 1
            total += p.stat().st_size
    return total, count


async def _audit_upload(session: AsyncSession, user_id: str, path: str, size: int, sha: str | None, outcome: str, reason: str | None) -> None:
    session.add(FileAuditEvent(user_id=user_id, action="upload", path=path[:512], size=size, sha256=sha, outcome=outcome, reason=(reason or None) and reason[:255]))
    await session.commit()
    logger.info("file.upload user=%s outcome=%s path=%s size=%d sha256=%s reason=%s", user_id, outcome, path, size, sha, reason)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    path: str = Query(default="", description="Target directory, relative to the user's workspace"),
) -> dict[str, Any]:
    """multipart/form-data with ONE field `file`. 201 {path, size}; 400/409/413/415/411 otherwise."""
    uid = current_user.id
    shown = f"{path.strip('/')}/<unknown>".lstrip("/")

    async def reject(code: int, detail: str, name: str | None = None, size: int = 0, sha: str | None = None):
        await _audit_upload(session, uid, f"{path.strip('/')}/{name}".lstrip("/") if name else shown, size, sha, "rejected", f"{code}: {detail}")
        raise HTTPException(code, detail)

    # Bound what the server must receive BEFORE parsing the multipart body (it is spooled to disk).
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        await reject(status.HTTP_411_LENGTH_REQUIRED, "Content-Length is required")
    if int(length) > MAX_UPLOAD_BYTES + MAX_REQUEST_SLACK:
        await reject(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds the {MAX_UPLOAD_BYTES // 1024} KB limit")

    try:
        form = await request.form(max_files=1, max_fields=1)
    except Exception:
        await reject(status.HTTP_400_BAD_REQUEST, "Malformed multipart body")
    upload = form.get("file")
    if not isinstance(upload, UploadFile) or len(form.keys()) != 1:
        await reject(status.HTTP_400_BAD_REQUEST, "Send exactly one multipart field named 'file'")

    try:
        name = _check_filename(upload.filename)
    except HTTPException as e:
        await reject(e.status_code, e.detail, name=(upload.filename or "")[:100].replace("/", "_").replace("\\", "_"))
        raise  # unreachable (reject raises)

    for seg in (x for x in path.split("/") if x):  # same rules as file names, for every directory segment
        if seg.startswith(".") or "\\" in seg or ".." in seg or not _NAME_OK.match(seg) or seg.lower() in _WIN_RESERVED:
            await reject(status.HTTP_400_BAD_REQUEST, "Invalid target directory", name=name)
    if "\\" in path or "\x00" in path:
        await reject(status.HTTP_400_BAD_REQUEST, "Invalid target directory", name=name)

    try:
        target_dir = _resolve_safe_path(uid, path)
    except ValueError as e:
        await reject(status.HTTP_400_BAD_REQUEST, str(e), name=name)
    sandbox = _get_sandbox_dir(uid)
    if target_dir.exists() and not target_dir.is_dir():
        await reject(status.HTTP_400_BAD_REQUEST, "Target path is not a directory", name=name)

    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    sha = hashlib.sha256(data).hexdigest()
    rel = (target_dir / name).relative_to(sandbox).as_posix()
    if len(data) > MAX_UPLOAD_BYTES:
        await reject(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds the {MAX_UPLOAD_BYTES // 1024} KB limit", name=name, size=len(data), sha=sha)
    if not data:
        await reject(status.HTTP_400_BAD_REQUEST, "Empty file", name=name)
    try:
        data.decode("utf-8")
        if b"\x00" in data:
            raise ValueError("NUL byte")
    except (UnicodeDecodeError, ValueError):
        await reject(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File must be UTF-8 text", name=name, size=len(data), sha=sha)

    target_dir.mkdir(parents=True, exist_ok=True)
    total, count = _workspace_usage(sandbox)
    if total + len(data) > WORKSPACE_QUOTA_BYTES or count + 1 > WORKSPACE_QUOTA_FILES:
        await reject(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Workspace quota exceeded", name=name, size=len(data), sha=sha)

    final = target_dir / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(final, flags, 0o600)  # atomic: fails if the name exists (even as a symlink)
    except FileExistsError:
        await reject(status.HTTP_409_CONFLICT, "A file with this name already exists", name=name, size=len(data), sha=sha)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        await _audit_upload(session, uid, rel, len(data), sha, "created", None)
    except Exception:
        final.unlink(missing_ok=True)  # never keep an upload we could not write or audit
        logger.exception("upload failed for user=%s path=%s", uid, rel)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Upload could not be completed")
    return {"path": rel, "size": len(data)}
