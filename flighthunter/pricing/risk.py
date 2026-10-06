"""Modèle de COÛT-RISQUE : espérance de dépense liée au risque d'un itinéraire.

Abu Dhabi et Tanzanie sont accessibles, mais leurs risques (retard, rebillet si
trop peu de passagers, fiabilité régionale) sont chiffrés en espérance
(probabilité × coût) et ajoutés au prix net → un vol "moins cher" mais risqué
peut devenir plus cher qu'un vol fiable une fois le risque intégré.
"""
from __future__ import annotations

from typing import Any

from ..models import FlightOption, RouteType


def _profile_expected_cost(profile: dict[str, Any]) -> tuple[float, list[str]]:
    total = 0.0
    lines: list[str] = []
    for ev in profile.get("events", []) or []:
        prob = float(ev.get("prob", 0))
        cost = float(ev.get("cost_eur", 0))
        exp = prob * cost
        total += exp
        lines.append(
            f"{ev.get('name', 'risque')} : {int(prob * 100)} % × {cost:.0f} € = {exp:.0f} €"
        )
    return total, lines


def _hubs_with_risk(opt: FlightOption, routes_cfg: dict[str, Any]) -> list[str]:
    """Hubs de l'itinéraire + hubs déduits des compagnies (ex. EY -> AUH)."""
    hubs = list(opt.hubs)
    hint = routes_cfg.get("carrier_hub_hint", {}) or {}
    for c in opt.carriers:
        h = hint.get(c)
        if h and h not in hubs:
            hubs.append(h)
    return hubs


def apply_risk(opt: FlightOption, routes_cfg: dict[str, Any]) -> float:
    """Calcule et attache le coût-risque à l'option. Renvoie l'espérance en €."""
    profiles = routes_cfg.get("risk_profiles", {}) or {}
    total = 0.0
    hubs = _hubs_with_risk(opt, routes_cfg)

    for hub in hubs:
        prof = profiles.get(hub)
        if not prof:
            continue
        exp, lines = _profile_expected_cost(prof)
        total += exp
        label = prof.get("label", hub)
        opt.warnings.append(
            f"RISQUE {label} (+{exp:.0f} € en espérance) : " + " ; ".join(lines)
        )
        if prof.get("note"):
            opt.warnings.append(prof["note"])

    # Fiabilité régionale : s'applique aux tronçons régionaux / chaînes multi-legs.
    regional = profiles.get("REGIONAL_SAFETY")
    if regional and opt.route_type in (RouteType.MULTI_LEG, RouteType.SELF_TRANSFER, RouteType.POSITIONING):
        exp, lines = _profile_expected_cost(regional)
        total += exp
        opt.warnings.append(
            f"RISQUE {regional.get('label', 'régional')} (+{exp:.0f} € en espérance) : "
            + " ; ".join(lines)
        )

    opt.risk_cost_eur = round(total, 2)
    return opt.risk_cost_eur
