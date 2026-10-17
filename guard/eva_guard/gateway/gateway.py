"""
Deterministic Policy Gateway.
Contract Version: 0.1.0
Owner: SEC-2 (Authority-side Security)
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from contracts.models import (
    CONTRACT_VERSION,
    AlignVerdict,
    ApprovalRequest,
    CheckActionRequest,
    CheckActionResponse,
    KillSwitchState,
    Provenance,
    ReasonCode,
    TaskPolicy,
    Trust,
)

logger = logging.getLogger(__name__)

# Standard known tool registry and schemas
TOOL_REGISTRY = {
    "gmail.search": {"required": ["query"], "read_only": True},
    "gmail.read": {"required": ["message_id"], "read_only": True},
    "gmail.draft": {"required": ["to", "subject", "body"], "read_only": False},
    "gmail.send": {"required": ["to", "subject", "body"], "read_only": False},
    "files.list": {"required": [], "read_only": True},
    "files.read": {"required": ["path"], "read_only": True},
    "files.search": {"required": ["query"], "read_only": True},
    "files.write": {"required": ["path", "content"], "read_only": False},
    "web.search": {"required": ["query"], "read_only": True},
    "web.fetch": {"required": ["url"], "read_only": True},
    "messages.history": {"required": [], "read_only": True},
    "messages.send": {"required": ["channel", "text"], "read_only": False},
}

DESTINATION_ARG_MAP = {
    "gmail.send": "to",
    "gmail.draft": "to",
    "web.fetch": "url",
    "files.read": "path",
    "files.write": "path",
}


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_action_hash(tool: str, args: dict[str, Any]) -> str:
    payload = {"tool": tool, "args": args}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_destination(dest: str) -> str:
    dest = dest.strip()
    if "@" in dest:
        return dest.lower()
    if dest.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(dest)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path
        return f"{scheme}://{netloc}{path}"
    return dest.lower()


def destination_matches(dest: str, pattern: str) -> bool:
    norm_dest = normalize_destination(dest)
    norm_pattern = normalize_destination(pattern)

    if norm_dest == norm_pattern:
        return True

    # Email domain wildcard: *@domain.com
    if norm_pattern.startswith("*@") and "@" in norm_dest:
        target_domain = norm_pattern[2:]
        dest_domain = norm_dest.split("@", 1)[1]
        return dest_domain == target_domain or target_domain == "*"

    # URL / path glob wildcard: https://* or https://domain/*
    if fnmatch.fnmatch(norm_dest, norm_pattern):
        return True

    return False


DEFAULT_APPROVAL_TTL_MINUTES = 10


def _approval_expiry(now: datetime, policy: Any, approvals_engine: Any) -> datetime:
    """An approval lives for the approval TTL (10 min), never longer than the task policy.

    No policy means nothing authorises the action: the approval is born expired (fail closed).
    """
    if policy is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    ttl = getattr(approvals_engine, "ttl_minutes", DEFAULT_APPROVAL_TTL_MINUTES)
    return min(now + timedelta(minutes=ttl), policy.expires_at)


class PolicyGateway:
    """
    Deterministic Policy Gateway implementing doc 02 §3 evaluation order.
    The single security authority. Deny by default.
    """

    def __init__(self, kill_switch: KillSwitchState | None = None) -> None:
        self.kill_switch = kill_switch or KillSwitchState(all_write_tools=False, tools=[], templates=[])

    def set_kill_switch(self, kill_switch: KillSwitchState) -> None:
        self.kill_switch = kill_switch

    def check(
        self,
        req: CheckActionRequest,
        policy: TaskPolicy | None,
        tier2_available: bool = True,
        approvals_engine: Any = None,
        align_client: Any = None,
        original_request: str | None = None,
    ) -> CheckActionResponse:
        """
        Runs the 11 gateway rules in exact order.
        Collects all failing reasons. First failing rule decides DENY/REQUIRE_APPROVAL.
        """
        event_id = f"gw-{uuid.uuid4().hex[:12]}"
        reasons: list[ReasonCode] = []
        is_side_effect = not req.read_only
        now = datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # Rule 1: Kill switch (tool / template / all write tools) -> DENY KILL_SWITCH
        # ------------------------------------------------------------------
        if self.kill_switch.all_write_tools and is_side_effect:
            reasons.append(ReasonCode.KILL_SWITCH)
        if req.tool in self.kill_switch.tools:
            reasons.append(ReasonCode.KILL_SWITCH)
        if policy and hasattr(policy, "origin") and policy.origin in self.kill_switch.templates:
            reasons.append(ReasonCode.KILL_SWITCH)

        # ------------------------------------------------------------------
        # Rule 2: Tool known in registry and args validate against schema
        # ------------------------------------------------------------------
        if req.tool not in TOOL_REGISTRY:
            reasons.append(ReasonCode.TOOL_UNKNOWN)
        else:
            meta = TOOL_REGISTRY[req.tool]
            for req_field in meta.get("required", []):
                if req_field not in req.args or req.args[req_field] is None:
                    reasons.append(ReasonCode.SCHEMA_INVALID)
                    break

        # ------------------------------------------------------------------
        # Rule 3: Policy present, not expired
        # ------------------------------------------------------------------
        if policy is None:
            reasons.append(ReasonCode.POLICY_EXPIRED)
        else:
            if policy.expires_at and policy.expires_at < now:
                reasons.append(ReasonCode.POLICY_EXPIRED)

        # ------------------------------------------------------------------
        # Rule 4: Tool in allowed_operations and not in prohibited_side_effects
        # ------------------------------------------------------------------
        if policy:
            if req.tool in policy.prohibited_side_effects:
                reasons.append(ReasonCode.TOOL_PROHIBITED)
            elif req.tool not in policy.allowed_operations:
                reasons.append(ReasonCode.TOOL_NOT_IN_POLICY)

        # ------------------------------------------------------------------
        # Rule 5: Args within allowed_data_scope
        # ------------------------------------------------------------------
        if policy and policy.allowed_data_scope:
            for scope in policy.allowed_data_scope:
                if req.tool.startswith(scope.tool_prefix):
                    arg_val = req.args.get(scope.field)
                    if arg_val and not fnmatch.fnmatch(str(arg_val), scope.pattern):
                        reasons.append(ReasonCode.ARG_OUT_OF_SCOPE)
                        break

        # ------------------------------------------------------------------
        # Rule 6: Destination args within allowed_destinations
        # ------------------------------------------------------------------
        dest_field = DESTINATION_ARG_MAP.get(req.tool)
        dest_val = req.args.get(dest_field) if dest_field else None
        if dest_val and policy:
            allowed = False
            for pat in policy.allowed_destinations:
                if destination_matches(str(dest_val), pat):
                    allowed = True
                    break
            if not allowed:
                reasons.append(ReasonCode.DESTINATION_NOT_ALLOWED)

        # ------------------------------------------------------------------
        # Rule 7: Provenance
        # A destination/recipient/URL arg whose provenance is UNTRUSTED and was not
        # typed by the user -> DENY if outside policy's destinations, otherwise REQUIRE_APPROVAL
        # ------------------------------------------------------------------
        untrusted_dest = False
        if dest_field and dest_val:
            prov = req.arg_provenance.get(dest_field)
            if prov and prov.trust == Trust.UNTRUSTED:
                # If outside policy destinations, rule 6 already catches or DENY
                if ReasonCode.DESTINATION_NOT_ALLOWED in reasons:
                    # Already denied
                    pass
                else:
                    untrusted_dest = True

        # ------------------------------------------------------------------
        # Rule 8: Posture check
        # if minimum_detector_posture == "tier2_required" and Tier 2 is down and tool is side effect
        # ------------------------------------------------------------------
        if policy and policy.minimum_detector_posture == "tier2_required" and not tier2_available and is_side_effect:
            reasons.append(ReasonCode.POSTURE_DEGRADED)

        # If any of Rules 1-8 produced a hard DENY reason:
        deny_reasons = [
            r for r in reasons if r in (
                ReasonCode.KILL_SWITCH,
                ReasonCode.TOOL_UNKNOWN,
                ReasonCode.SCHEMA_INVALID,
                ReasonCode.POLICY_EXPIRED,
                ReasonCode.TOOL_PROHIBITED,
                ReasonCode.TOOL_NOT_IN_POLICY,
                ReasonCode.ARG_OUT_OF_SCOPE,
                ReasonCode.DESTINATION_NOT_ALLOWED,
                ReasonCode.POSTURE_DEGRADED,
            )
        ]

        if deny_reasons:
            return CheckActionResponse(
                decision="DENY",
                reasons=deny_reasons,
                reason_text=f"Action denied by deterministic gateway: {', '.join(r.value for r in deny_reasons)}",
                align={"verdict": "unavailable", "score": None},
                approval=None,
                contract_version=CONTRACT_VERSION,
                event_id=event_id,
            )

        # Check approval status if an approval_id was provided
        approval_obj: ApprovalRequest | None = None
        action_hash = compute_action_hash(req.tool, req.args)

        if req.approval_id:
            if approvals_engine is not None:
                is_valid, app_rec, mismatch = approvals_engine.verify_approval(
                    req.approval_id, req.tool, req.args, action_hash
                )
                if not is_valid:
                    if mismatch:
                        return CheckActionResponse(
                            decision="DENY",
                            reasons=[ReasonCode.APPROVAL_MISMATCH],
                            reason_text="Action arguments do not match approved action hash",
                            align={"verdict": "misaligned", "score": 0.0},
                            approval=None,
                            contract_version=CONTRACT_VERSION,
                            event_id=event_id,
                        )
                    else:
                        return CheckActionResponse(
                            decision="DENY",
                            reasons=[ReasonCode.APPROVAL_REQUIRED],
                            reason_text="Approval expired or invalid",
                            align={"verdict": "unavailable", "score": None},
                            approval=None,
                            contract_version=CONTRACT_VERSION,
                            event_id=event_id,
                        )
                # Approval is valid!
                return CheckActionResponse(
                    decision="ALLOW",
                    reasons=[],
                    reason_text="Action approved by human and verified by gateway",
                    align={"verdict": "aligned", "score": 1.0},
                    approval=None,
                    contract_version=CONTRACT_VERSION,
                    event_id=event_id,
                )

        # ------------------------------------------------------------------
        # Rule 7 (provenance approval) & Rule 9 (approval_required_for)
        # ------------------------------------------------------------------
        needs_approval = False
        approval_reasons: list[ReasonCode] = []

        if untrusted_dest:
            needs_approval = True
            approval_reasons.append(ReasonCode.UNTRUSTED_ARG_PROVENANCE)

        if policy and req.tool in policy.approval_required_for:
            needs_approval = True
            approval_reasons.append(ReasonCode.APPROVAL_REQUIRED)

        if needs_approval:
            approval_id = f"appr-{uuid.uuid4().hex[:10]}"
            arg_sources = {
                k: "typed by user" if prov.trust == Trust.USER else f"untrusted from {prov.source_type.value} ({prov.source_id})"
                for k, prov in req.arg_provenance.items()
            }
            approval_obj = ApprovalRequest(
                approval_id=approval_id,
                task_id=req.task_id,
                exact_action={"tool": req.tool, "args": req.args},
                arg_sources=arg_sources,
                action_hash=action_hash,
                expires_at=_approval_expiry(now, policy, approvals_engine),
            )
            if approvals_engine is not None:
                approvals_engine.register_approval(approval_obj)

            return CheckActionResponse(
                decision="REQUIRE_APPROVAL",
                reasons=approval_reasons,
                reason_text=f"Human approval required: {', '.join(r.value for r in approval_reasons)}",
                align={"verdict": "aligned", "score": 0.95},
                approval=approval_obj,
                contract_version=CONTRACT_VERSION,
                event_id=event_id,
            )

        # ------------------------------------------------------------------
        # Rule 10: ALIGN (Advisory check)
        # Advisory only: misaligned on otherwise ALLOW -> downgrade to REQUIRE_APPROVAL (ALIGN_MISALIGNED)
        # uncertain/unavailable on side-effect tool -> REQUIRE_APPROVAL (ALIGN_UNCERTAIN)
        # ALIGN can NEVER upgrade.
        # ------------------------------------------------------------------
        align_info: dict[str, Any] = {"verdict": "aligned", "score": 1.0}
        if align_client is not None and original_request:
            align_res = align_client.check(original_request, policy, req.tool, req.args)
            align_info = {"verdict": align_res.verdict, "score": align_res.score}

            if align_res.verdict == "misaligned":
                approval_id = f"appr-{uuid.uuid4().hex[:10]}"
                approval_obj = ApprovalRequest(
                    approval_id=approval_id,
                    task_id=req.task_id,
                    exact_action={"tool": req.tool, "args": req.args},
                    arg_sources={},
                    action_hash=action_hash,
                    expires_at=policy.expires_at if policy else now,
                )
                if approvals_engine is not None:
                    approvals_engine.register_approval(approval_obj)
                return CheckActionResponse(
                    decision="REQUIRE_APPROVAL",
                    reasons=[ReasonCode.ALIGN_MISALIGNED],
                    reason_text="Action flagged as misaligned with user intent by ALIGN check",
                    align=align_info,
                    approval=approval_obj,
                    contract_version=CONTRACT_VERSION,
                    event_id=event_id,
                )
            elif align_res.verdict in ("uncertain", "unavailable") and is_side_effect:
                approval_id = f"appr-{uuid.uuid4().hex[:10]}"
                approval_obj = ApprovalRequest(
                    approval_id=approval_id,
                    task_id=req.task_id,
                    exact_action={"tool": req.tool, "args": req.args},
                    arg_sources={},
                    action_hash=action_hash,
                    expires_at=policy.expires_at if policy else now,
                )
                if approvals_engine is not None:
                    approvals_engine.register_approval(approval_obj)
                return CheckActionResponse(
                    decision="REQUIRE_APPROVAL",
                    reasons=[ReasonCode.ALIGN_UNCERTAIN],
                    reason_text="Action intent is uncertain on side-effect tool; human approval required",
                    align=align_info,
                    approval=approval_obj,
                    contract_version=CONTRACT_VERSION,
                    event_id=event_id,
                )

        # ------------------------------------------------------------------
        # Rule 11: Otherwise ALLOW
        # ------------------------------------------------------------------
        return CheckActionResponse(
            decision="ALLOW",
            reasons=[],
            reason_text=f"Action '{req.tool}' permitted by policy",
            align=align_info,
            approval=None,
            contract_version=CONTRACT_VERSION,
            event_id=event_id,
        )
