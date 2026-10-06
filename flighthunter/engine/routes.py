"""Règles de routage : hubs autorisés/exclus/signalés, types de routes actifs."""
from __future__ import annotations

from typing import Any, Optional

from ..models import Alert, FlightOption, RouteType


def allowed_hubs(routes_cfg: dict[str, Any]) -> list[str]:
    allowed = list(routes_cfg.get("allowed_hubs", []))
    excluded = set(routes_cfg.get("excluded_hubs", []))
    return [h for h in allowed if h not in excluded]


def hub_warning(hub: str, routes_cfg: dict[str, Any]) -> Optional[str]:
    return (routes_cfg.get("flagged_hubs", {}) or {}).get(hub)


def enabled_route_types(alert: Alert) -> list[RouteType]:
    t = alert.techniques
    types: list[RouteType] = []
    if t.through_fare:
        types.append(RouteType.THROUGH)
    if t.self_transfer:
        types.append(RouteType.SELF_TRANSFER)
    if t.positioning:
        types.append(RouteType.POSITIONING)
    if t.open_jaw:
        types.append(RouteType.OPEN_JAW)
    if t.hidden_city:
        types.append(RouteType.HIDDEN_CITY)
    return types or [RouteType.THROUGH]


def apply_hub_rules(
    option: FlightOption, routes_cfg: dict[str, Any]
) -> Optional[FlightOption]:
    """Écarte les options passant par un hub exclu ; annote les hubs signalés."""
    excluded = set(routes_cfg.get("excluded_hubs", []))
    for hub in option.hubs:
        if hub in excluded:
            return None
        warn = hub_warning(hub, routes_cfg)
        if warn:
            option.warnings.append(warn)

    if option.route_type == RouteType.SELF_TRANSFER:
        st = routes_cfg.get("self_transfer", {}) or {}
        if st.get("warn_no_interline_protection", True):
            option.warnings.append(
                "Billets séparés : aucune protection interligne. "
                "Une correspondance ratée est à votre charge — prévoyez de la marge."
            )
    return option
