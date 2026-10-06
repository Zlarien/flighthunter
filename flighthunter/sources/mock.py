"""Source DEMO : génère des prix réalistes (sans aucune clé API).

But : permettre de tester tout le pipeline immédiatement. Les prix sont
pseudo-aléatoires mais DÉTERMINISTES (dérivés d'un hash), donc reproductibles
d'une exécution à l'autre — ce qui rend la détection d'anomalies testable.
"""
from __future__ import annotations

import hashlib
from datetime import date

from ..config import Settings
from ..engine.routes import allowed_hubs, enabled_route_types
from ..models import Alert, FlightOption, RouteType
from .base import Source

# Tarif de base indicatif Paris -> Moroni par hub (EUR), full-service
_HUB_BASE = {"NBO": 780, "ADD": 820, "IST": 860, "RUN": 950}
_HUB_CARRIER = {"NBO": "KQ", "ADD": "ET", "IST": "TK", "RUN": "UU"}
_ORIGIN_ADJ = {"CDG": 0, "ORY": 5, "BVA": -45, "CRL": -55, "BRU": -20, "BGY": -60}
_ROUTE_MULT = {
    RouteType.THROUGH: 1.00,
    RouteType.OPEN_JAW: 0.90,
    RouteType.SELF_TRANSFER: 0.82,
    RouteType.POSITIONING: 0.78,
    RouteType.HIDDEN_CITY: 0.70,
}


def _pseudo(*parts: object) -> float:
    """Réel déterministe dans [0, 1) dérivé d'un hash des arguments."""
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.md5(raw).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _season_adj(d: date) -> float:
    # Juillet/août = haute saison (plus cher) ; juin/sept = épaules.
    return {6: -30, 7: 130, 8: 110, 9: -20}.get(d.month, 0)


class MockSource(Source):
    name = "mock"

    def search(
        self,
        alert: Alert,
        date_pairs: list[tuple[date, date]],
        settings: Settings,
    ) -> list[FlightOption]:
        hubs = allowed_hubs(settings.routes) or ["NBO"]
        route_types = enabled_route_types(alert)
        options: list[FlightOption] = []

        for dep, ret in date_pairs:
            nights = (ret - dep).days
            for origin in alert.origins:
                for rt in route_types:
                    hub = min(
                        hubs,
                        key=lambda h: _HUB_BASE.get(h, 900) + 60 * _pseudo(origin, h, dep, rt),
                    )
                    base = _HUB_BASE.get(hub, 900) + _ORIGIN_ADJ.get(origin, 0)
                    price = base * _ROUTE_MULT[rt] + _season_adj(dep)
                    price += 160 * _pseudo(origin, hub, dep, ret, rt) - 60  # bruit ±

                    # Erreur de prix rare (~2 %)
                    is_error = _pseudo("err", origin, hub, dep, rt) > 0.98
                    if is_error:
                        price = 430 + 90 * _pseudo("errval", dep, rt)

                    # Bagage : full-service (through/open_jaw) souvent inclus,
                    # billets séparés/positioning rarement.
                    included = rt in (RouteType.THROUGH, RouteType.OPEN_JAW) and not is_error
                    addon = 0.0 if included else 55.0 + 20 * _pseudo("bag", hub)

                    return_airport = origin
                    if rt == RouteType.OPEN_JAW and len(alert.origins) > 1:
                        return_airport = alert.origins[
                            (alert.origins.index(origin) + 1) % len(alert.origins)
                        ]

                    opt = FlightOption(
                        origin=origin,
                        destination=alert.destination,
                        outbound_date=dep,
                        return_date=ret,
                        return_airport=return_airport,
                        route_type=rt,
                        hubs=[hub],
                        carriers=[_HUB_CARRIER.get(hub, "??")],
                        price_eur=round(price, 2),
                        baggage_included=included,
                        baggage_addon_eur=round(addon, 2),
                        stay_nights=nights,
                        source=self.name,
                        booking_url=f"https://www.google.com/travel/flights?q={origin}+{alert.destination}+{dep}",
                        is_error_fare=is_error,
                    )
                    if is_error:
                        opt.warnings.append(
                            "Erreur de prix probable : à confirmer immédiatement, "
                            "peut être annulée par la compagnie. Évitez les frais non remboursables."
                        )
                    if rt == RouteType.HIDDEN_CITY:
                        opt.warnings.append(
                            "Hidden-city : cabine seule, non répétable, contraire aux CGV de certaines compagnies."
                        )
                    if rt == RouteType.POSITIONING:
                        opt.warnings.append(
                            "Vol de positionnement : billets séparés, prévoyez une nuit de marge au hub."
                        )
                    options.append(opt)
        return options
