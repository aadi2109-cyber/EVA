"""
Reset the eval environment to seed state.
Usage: python -m app.eval.reset

Restores the mock mailbox/outbox/drafts/http log and workspace seed files, wipes
per-user eval sandboxes, and drops the cached guard client. Refuses to run
unless APP_ENV=eval (it deletes files).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from app.config import settings
from app.eval import hooks
from env.mock.reset import reset_mock_environment


def reset_eval_environment() -> None:
    if not hooks.eval_active():
        raise RuntimeError("reset is only permitted when APP_ENV=eval")
    reset_mock_environment()

    sandbox = Path(settings.WORKSPACE_ROOT) / "eval-user"
    if sandbox.exists():
        shutil.rmtree(sandbox)

    from app.guard_client.factory import set_guard_client

    set_guard_client(None)


def main() -> int:
    try:
        reset_eval_environment()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
