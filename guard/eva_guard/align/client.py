"""
ALIGN Client implementation.
Advisory Action Intent Alignment.
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from contracts.models import AlignVerdict, TaskPolicy

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
URL_REGEX = re.compile(r"https?://[^\s]+")


class AlignClient:
    """
    Advisory action intent alignment client.
    Evaluates whether proposed tool actions align with the user's original request.
    Never uses retrieved content. Can only downgrade permissions, never grant them.
    """

    def __init__(
        self,
        enabled: bool | None = None,
        timeout_ms: int | None = None,
        backend: Any = None,
    ) -> None:
        # `backend(original_request, policy, tool, args) -> AlignVerdict` is the swappable
        # implementation (e.g. a LAYA typed-question client). Default: deterministic heuristic.
        self._backend = backend or self._heuristic
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="align")
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("ALIGN_ENABLED", "true").lower() in ("true", "1")
        )
        self.timeout_ms = (
            timeout_ms
            if timeout_ms is not None
            else int(os.getenv("ALIGN_TIMEOUT_MS", "1500"))
        )

    def is_available(self) -> bool:
        return self.enabled

    def check(
        self,
        original_request: str,
        policy: TaskPolicy | None,
        tool: str,
        args: dict[str, Any],
    ) -> AlignVerdict:
        """
        Advisory check with a hard timeout. Any timeout or backend error -> "unavailable"
        (the gateway then asks for approval on side effects; ALIGN can never grant ALLOW).
        """
        if not self.enabled:
            return AlignVerdict(verdict="unavailable", score=None)
        fut = self._pool.submit(self._backend, original_request, policy, tool, args)
        try:
            return fut.result(timeout=self.timeout_ms / 1000)
        except FutureTimeout:
            logger.warning("ALIGN check timed out (> %s ms)", self.timeout_ms)
        except Exception as e:  # noqa: BLE001
            logger.warning("ALIGN backend error: %s", e)
        return AlignVerdict(verdict="unavailable", score=None)

    def _heuristic(
        self,
        original_request: str,
        policy: TaskPolicy | None,
        tool: str,
        args: dict[str, Any],
    ) -> AlignVerdict:
        start_time = time.perf_counter()
        req_lower = original_request.lower()

        # Destination checks
        dest_in_args: str | None = None
        if "to" in args:
            dest_in_args = str(args["to"]).lower()
        elif "url" in args:
            dest_in_args = str(args["url"]).lower()

        if dest_in_args:
            # If the action sends to a destination, did the user explicitly name it in their request?
            user_emails = [e.lower() for e in EMAIL_REGEX.findall(req_lower)]
            user_urls = [u.lower() for u in URL_REGEX.findall(req_lower)]
            user_named_dests = set(user_emails + user_urls)

            # Check if destination contains attacker keywords or is completely unmentioned
            if any(k in dest_in_args for k in ["attacker", "evil", "exfil", "pastebin"]):
                return AlignVerdict(verdict="misaligned", score=0.0)

            if user_named_dests and dest_in_args not in user_named_dests:
                # User named specific destinations, but this is a different one!
                return AlignVerdict(verdict="misaligned", score=0.1)

        # Action intent contradiction checks
        is_write = tool in ("gmail.send", "messages.send", "telegram.send", "files.write")
        user_wants_read_only = any(
            k in req_lower for k in ["summarize", "read", "list", "show", "search", "check"]
        ) and not any(k in req_lower for k in ["send", "write", "post", "forward", "email"])

        if is_write and user_wants_read_only:
            return AlignVerdict(verdict="misaligned", score=0.05)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if elapsed_ms > self.timeout_ms:
            logger.warning(f"ALIGN check timed out ({elapsed_ms:.1f}ms > {self.timeout_ms}ms)")
            return AlignVerdict(verdict="unavailable", score=None)

        return AlignVerdict(verdict="aligned", score=0.98)
