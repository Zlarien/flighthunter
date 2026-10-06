"""Estimation du cashback / commission affiliée récupérable (prix NET)."""
from __future__ import annotations

from ..models import FlightOption, RouteType

# Taux indicatif de cashback récupérable via affiliation/portails (éditable).
DEFAULT_RATE = 0.02


def estimate_cashback(option: FlightOption, rate: float = DEFAULT_RATE) -> float:
    """Cashback estimé. Nul pour les cas non affiliables (erreurs de prix, hidden-city)."""
    if option.is_error_fare or option.route_type == RouteType.HIDDEN_CITY:
        return 0.0
    return round(option.price_eur * rate, 2)
