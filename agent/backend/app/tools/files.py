"""
Sandboxed file tools: files.list, files.read, files.search, files.write.
Strictly confined to WORKSPACE_ROOT/<user_id>/, preventing path traversal and symlink escapes.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from contracts.models import Provenance, ScanField, SourceType, Trust
from app.config import settings
from app.tools.base import ToolContext, ToolExecutionResult
from env.mock.state import state as mock_state

MAX_FILE_BYTES = 512 * 1024  # 512 KB cap


def _get_sandbox_dir(user_id: str) -> Path:
    base = Path(settings.WORKSPACE_ROOT).resolve()
    sandbox = (base / user_id).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


def _resolve_safe_path(user_id: str, relative_path: str) -> Path:
    sandbox = _get_sandbox_dir(user_id)
    # Strip any leading slashes/backslashes to ensure relative resolution
    clean_rel = relative_path.lstrip("/\\")
    resolved = (sandbox / clean_rel).resolve()

    # Security check: must remain within sandbox root
    try:
        resolved.relative_to(sandbox)
    except ValueError:
        raise ValueError(f"Path traversal detected: path '{relative_path}' escapes sandbox root")

    return resolved


# ------------------------------------------------------------------------------
# 1. files.list
# ------------------------------------------------------------------------------
class FilesListArgs(BaseModel):
    path: str = Field(default="", description="Relative directory path to list")


class FilesListTool:
    name = "files.list"
    description = "List files and directories in the user's sandboxed workspace."
    args_schema = FilesListArgs
    read_only = True
    risk_class = "read"
    destination_args = ["path"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = FilesListArgs.model_validate(args)
        target = _resolve_safe_path(context.user_id, validated.path)
        if not target.exists() or not target.is_dir():
            entries = []
        else:
            entries = [
                {"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
                for p in target.iterdir()
            ]

        def _describe(e: dict[str, Any]) -> str:
            kind = "dir" if e["is_dir"] else str(e["size"]) + " B"
            return f"{e['name']} ({kind})"

        summary_text = "\n".join(_describe(e) for e in entries)
        scan_field = ScanField(
            name="file_list",
            text=summary_text or "[Empty directory]",
            provenance=Provenance(
                source_id=str(target),
                source_type=SourceType.FILE,
                field="file_list",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"entries": entries},
            text_summary=summary_text,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 2. files.read
# ------------------------------------------------------------------------------
class FilesReadArgs(BaseModel):
    path: str = Field(..., description="Relative path of file to read")


def _resolve_mock_workspace() -> Path:
    candidates = [
        Path("env/mock/workspace"),
        Path(__file__).resolve().parents[4] / "env" / "mock" / "workspace",
        Path(__file__).resolve().parents[3] / "env" / "mock" / "workspace",
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("env/mock/workspace")


class FilesReadTool:
    name = "files.read"
    description = "Read the content of a file in the user's sandboxed workspace."
    args_schema = FilesReadArgs
    read_only = True
    risk_class = "read"
    destination_args = ["path"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = FilesReadArgs.model_validate(args)
        target = _resolve_safe_path(context.user_id, validated.path)

        if not target.exists() or not target.is_file():
            # In mock mode, if file not yet copied to user sandbox, check env/mock/workspace
            mock_ws = _resolve_mock_workspace()
            mock_file = mock_ws / validated.path.lstrip("/\\")
            if mock_file.exists() and mock_file.is_file():
                content = mock_file.read_text(encoding="utf-8", errors="replace")
                target = mock_file
            else:
                raise FileNotFoundError(f"File not found: {validated.path}")
        else:
            if target.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"File size exceeds maximum allowed limit of {MAX_FILE_BYTES} bytes")
            content = target.read_text(encoding="utf-8", errors="replace")

        scan_field = ScanField(
            name="content",
            text=content,
            provenance=Provenance(
                source_id=str(target.name),
                source_type=SourceType.FILE,
                field="content",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"content": content, "path": validated.path},
            text_summary=content,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 3. files.search
# ------------------------------------------------------------------------------
class FilesSearchArgs(BaseModel):
    query: str = Field(..., description="Text query to search for across files")
    path: str = Field(default="", description="Optional subdirectory to restrict search")


class FilesSearchTool:
    name = "files.search"
    description = "Search across text files in the user's sandboxed workspace."
    args_schema = FilesSearchArgs
    read_only = True
    risk_class = "read"
    destination_args = ["path"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = FilesSearchArgs.model_validate(args)
        target_dir = _resolve_safe_path(context.user_id, validated.path)

        matches = []
        if target_dir.exists() and target_dir.is_dir():
            for p in target_dir.rglob("*"):
                if p.is_file() and p.stat().st_size <= MAX_FILE_BYTES:
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                        if validated.query.lower() in text.lower():
                            matches.append({"file": p.name, "snippet": text[:200]})
                    except Exception:
                        pass

        # Also search env/mock/workspace if matches empty
        if not matches:
            mock_ws = _resolve_mock_workspace()
            if mock_ws.exists():
                for p in mock_ws.rglob("*"):
                    if p.is_file():
                        try:
                            text = p.read_text(encoding="utf-8", errors="replace")
                            if validated.query.lower() in text.lower():
                                matches.append({"file": p.name, "snippet": text[:200]})
                        except Exception:
                            pass

        summary_text = "\n".join([f"{m['file']}: {m['snippet']}" for m in matches]) or "No matching files found."
        scan_field = ScanField(
            name="search_results",
            text=summary_text,
            provenance=Provenance(
                source_id=f"search:{validated.query}",
                source_type=SourceType.FILE,
                field="search_results",
                retrieval_path=[context.call_id],
                trust=Trust.UNTRUSTED,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"matches": matches},
            text_summary=summary_text,
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()


# ------------------------------------------------------------------------------
# 4. files.write
# ------------------------------------------------------------------------------
class FilesWriteArgs(BaseModel):
    path: str = Field(..., description="Relative destination file path")
    content: str = Field(..., description="Content to write to file")


class FilesWriteTool:
    name = "files.write"
    description = "Write or overwrite a file in the user's sandboxed workspace."
    args_schema = FilesWriteArgs
    read_only = False
    risk_class = "write_low"
    destination_args = ["path"]

    async def run(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        validated = FilesWriteArgs.model_validate(args)
        target = _resolve_safe_path(context.user_id, validated.path)

        if len(validated.content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"Content size exceeds maximum allowed write limit of {MAX_FILE_BYTES} bytes")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(validated.content, encoding="utf-8")

        # Compute hash and record in mock state
        file_hash = hashlib.sha256(validated.content.encode("utf-8")).hexdigest()
        obs = mock_state.observe_state()
        hashes = obs.get("file_hashes", {})
        hashes[target.name] = file_hash
        mock_state.set_custom_state("file_hashes", hashes)

        scan_field = ScanField(
            name="status",
            text=f"Successfully wrote {len(validated.content)} characters to {validated.path}",
            provenance=Provenance(
                source_id=str(target.name),
                source_type=SourceType.TOOL_OUTPUT,
                field="status",
                retrieval_path=[context.call_id],
                trust=Trust.SYSTEM,
            ),
        )

        return ToolExecutionResult(
            call_id=context.call_id,
            tool_name=self.name,
            scan_fields=[scan_field],
            raw_output={"path": validated.path, "bytes_written": len(validated.content), "hash": file_hash},
            text_summary=f"Wrote {validated.path}",
        )

    def observe_state(self) -> dict[str, Any]:
        return mock_state.observe_state()
