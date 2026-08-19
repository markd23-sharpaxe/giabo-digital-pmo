"""Renders `ui/pm_veto_card.json`'s Adaptive Card template against a concrete
`PendingChangePayload`.

Substitution happens on the *parsed* JSON tree's string values, not on the
raw template text, so a `prince2_impact_assessment` containing a `"` or a
newline can't corrupt the card's JSON structure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maf_graph_state import PendingChangePayload, RiskEscalationPayload

_CARD_TEMPLATE_PATH = Path(__file__).parent / "pm_veto_card.json"
_EXCEPTION_CARD_TEMPLATE_PATH = Path(__file__).parent / "exception_card.json"

_PLACEHOLDERS = {
    "${change_id}": lambda p: p.change_id,
    "${target_table}": lambda p: p.target_table,
    "${record_id}": lambda p: p.record_id,
    "${prince2_impact_assessment}": lambda p: p.prince2_impact_assessment,
}

_EXCEPTION_PLACEHOLDERS = {
    "${exception_id}": lambda exception_id, risk: exception_id,
    "${risk_category}": lambda exception_id, risk: risk.risk_category,
    "${severity}": lambda exception_id, risk: risk.severity,
    "${description}": lambda exception_id, risk: risk.description,
}


def _substitute(node: Any, values: dict) -> Any:
    """`values` maps each `${...}` placeholder to its already-resolved
    replacement string -- resolution happens once, up front, in the caller,
    so this function stays a simple, reusable string-substitution walk."""
    if isinstance(node, str):
        for placeholder, value in values.items():
            if placeholder in node:
                node = node.replace(placeholder, value)
        return node
    if isinstance(node, dict):
        return {key: _substitute(value, values) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute(item, values) for item in node]
    return node


def render_pm_veto_card(payload: PendingChangePayload) -> dict:
    """Fill in `pm_veto_card.json`'s `${...}` placeholders for one pending change.

    Returns a plain dict (the Adaptive Card JSON) ready to hand to whatever
    surface actually posts it to Teams (`json.dumps(...)` if a raw string
    payload is needed).
    """
    template = json.loads(_CARD_TEMPLATE_PATH.read_text(encoding="utf-8"))
    values = {placeholder: str(extract(payload)) for placeholder, extract in _PLACEHOLDERS.items()}
    return _substitute(template, values)


def render_exception_card(exception_id: str, risk: RiskEscalationPayload) -> dict:
    """Fill in `exception_card.json`'s `${...}` placeholders for one PRINCE2
    exception. `exception_id` is minted by `StateWritebackNode` (not part of
    `RiskEscalationPayload`'s strict schema) and doubles as both the
    `ctx.request_info` `request_id` and this card's Action.Submit correlator.
    """
    template = json.loads(_EXCEPTION_CARD_TEMPLATE_PATH.read_text(encoding="utf-8"))
    values = {
        placeholder: str(extract(exception_id, risk)) for placeholder, extract in _EXCEPTION_PLACEHOLDERS.items()
    }
    return _substitute(template, values)
