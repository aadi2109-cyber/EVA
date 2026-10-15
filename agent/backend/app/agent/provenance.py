"""
Argument provenance tracker for EVA Agent Backend.
Determines whether tool arguments originate from the authenticated user's typed request
or external untrusted tool outputs. Fails safe by classifying uncertain values as UNTRUSTED.
"""

from __future__ import annotations

from typing import Any
from contracts.models import Provenance, SourceType, Trust


class ProvenanceTracker:
    def __init__(self, task_id: str, user_request: str) -> None:
        self.task_id = task_id
        self.user_request = user_request.strip()
        # Track untrusted text fragments discovered from tool outputs
        self._untrusted_fragments: list[tuple[str, str, SourceType]] = []  # (text, source_id, source_type)

    def record_tool_output(self, source_id: str, source_type: SourceType, text: str) -> None:
        """Record output text to track subsequent provenance propagation."""
        if text and len(text.strip()) > 3:
            self._untrusted_fragments.append((text.strip(), source_id, source_type))

    def compute_arg_provenance(self, tool_name: str, args: dict[str, Any]) -> dict[str, Provenance]:
        provenances: dict[str, Provenance] = {}

        for arg_name, arg_val in args.items():
            str_val = str(arg_val).strip()

            # 1. Exact or clear substring of user's original typed request
            if str_val and (str_val.lower() in self.user_request.lower() or self.user_request.lower() in str_val.lower()):
                provenances[arg_name] = Provenance(
                    source_id=self.task_id,
                    source_type=SourceType.USER_REQUEST,
                    field=arg_name,
                    retrieval_path=[],
                    trust=Trust.USER,
                )
                continue

            # 2. Check if matches any previously retrieved untrusted tool outputs
            found_untrusted = False
            for frag, src_id, src_type in self._untrusted_fragments:
                if str_val and (str_val.lower() in frag.lower()):
                    provenances[arg_name] = Provenance(
                        source_id=src_id,
                        source_type=src_type,
                        field=arg_name,
                        retrieval_path=[],
                        trust=Trust.UNTRUSTED,
                    )
                    found_untrusted = True
                    break

            if found_untrusted:
                continue

            # 3. Default to UNTRUSTED for safety
            provenances[arg_name] = Provenance(
                source_id="untrusted_origin",
                source_type=SourceType.TOOL_OUTPUT,
                field=arg_name,
                retrieval_path=[],
                trust=Trust.UNTRUSTED,
            )

        return provenances
