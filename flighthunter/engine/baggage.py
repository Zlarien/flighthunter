"""Gestion du bagage : filtrage et coût effectif selon la politique de l'alerte."""
from __future__ import annotations

from ..models import Baggage, FlightOption, RouteType


def baggage_ok(option: FlightOption, policy: Baggage) -> bool:
    """L'option est-elle compatible avec la politique bagage de l'alerte ?"""
    if policy == Baggage.CHECKED_REQUIRED:
        # Hidden-city interdit avec bagage soute (le bagage part à la mauvaise dest.)
        if option.route_type == RouteType.HIDDEN_CITY:
            return False
    return True


def effective_baggage_cost(option: FlightOption, policy: Baggage) -> float:
    """Supplément bagage à intégrer au prix net selon la politique choisie."""
    if policy == Baggage.CABIN_ONLY:
        return 0.0
    if policy == Baggage.CHECKED_REQUIRED:
        return 0.0 if option.baggage_included else option.baggage_addon_eur
    # ANY : on ne force pas le bagage ; on le signale seulement.
    if not option.baggage_included and option.baggage_addon_eur:
        option.warnings.append(
            f"Bagage soute non inclus (+{option.baggage_addon_eur:.0f} € si besoin)."
        )
    return 0.0
