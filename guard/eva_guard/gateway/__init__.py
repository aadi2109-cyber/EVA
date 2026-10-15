"""
Deterministic Policy Gateway module.
Owner: SEC-2 (Authority-side Security)
"""

from .gateway import (
    PolicyGateway,
    TOOL_REGISTRY,
    canonical_json,
    compute_action_hash,
    destination_matches,
    normalize_destination,
)

__all__ = [
    "PolicyGateway",
    "TOOL_REGISTRY",
    "canonical_json",
    "compute_action_hash",
    "destination_matches",
    "normalize_destination",
]
