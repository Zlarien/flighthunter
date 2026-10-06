"""Calcul du prix NET porte-à-porte : vol + bagage + accès sol - cashback."""
from __future__ import annotations

from ..config import Settings
from ..engine.baggage import baggage_ok, effective_baggage_cost
from ..engine.ground import ground_access
from ..engine.routes import apply_hub_rules
from ..models import Alert, FlightOption, RouteType
from .cashback import estimate_cashback
from .risk import apply_risk


def normalize(
    options: list[FlightOption], alert: Alert, settings: Settings
) -> list[FlightOption]:
    """Filtre selon les règles et calcule net_price_eur pour chaque option."""
    result: list[FlightOption] = []
    for opt in options:
        if not baggage_ok(opt, alert.baggage):
            continue
        if apply_hub_rules(opt, settings.routes) is None:
            continue

        bag_cost = effective_baggage_cost(opt, alert.baggage)

        ground_cost = 0.0
        is_multileg = opt.route_type == RouteType.MULTI_LEG
        # Les chaînes multi-legs intègrent déjà sol + hébergement dans extra_costs_eur.
        if alert.techniques.ground_multimodal and not is_multileg:
            g = ground_access(opt.origin, settings)
            if g:
                opt.ground = g
                ground_cost += g.cost_eur
            if opt.return_airport and opt.return_airport != opt.origin:
                gr = ground_access(opt.return_airport, settings)
                if gr:
                    ground_cost += gr.cost_eur

        cashback = 0.0 if is_multileg else estimate_cashback(opt)
        opt.cashback_eur = cashback

        risk = apply_risk(opt, settings.routes)

        opt.net_price_eur = round(
            opt.price_eur + bag_cost + ground_cost + opt.extra_costs_eur + risk - cashback, 2
        )
        result.append(opt)
    return result
