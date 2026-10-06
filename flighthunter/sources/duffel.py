"""Source Duffel (tarifs live réservables, NDC). Activée si DUFFEL_TOKEN présent.

Duffel facture les recherches au-delà d'un ratio recherche/réservation : on borne
donc le nombre de paires interrogées. Prêt à l'emploi dès que vous ajoutez le token.
Docs : https://duffel.com/docs/api
"""
from __future__ import annotations

from datetime import date

import httpx

from ..config import Settings
from ..models import Alert, FlightOption, RouteType
from .base import Source

_ENDPOINT = "https://api.duffel.com/air/offer_requests"
_MAX_PAIRS = 6  # borne stricte pour maîtriser les coûts de recherche


class DuffelSource(Source):
    name = "duffel"

    def __init__(self, token: str) -> None:
        self.token = token

    def search(
        self, alert: Alert, date_pairs: list[tuple[date, date]], settings: Settings
    ) -> list[FlightOption]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        out: list[FlightOption] = []
        pairs = date_pairs[:_MAX_PAIRS]
        try:
            with httpx.Client(timeout=40, headers=headers) as client:
                for origin in alert.origins[:2]:
                    for dep, ret in pairs:
                        out.extend(self._offer_request(client, alert, origin, dep, ret))
        except Exception as exc:  # noqa: BLE001
            print(f"[duffel] requête échouée, ignorée : {exc}")
        return out

    def _offer_request(self, client, alert, origin, dep, ret) -> list[FlightOption]:
        body = {
            "data": {
                "slices": [
                    {"origin": origin, "destination": alert.destination,
                     "departure_date": dep.isoformat()},
                    {"origin": alert.destination, "destination": origin,
                     "departure_date": ret.isoformat()},
                ],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }
        }
        resp = client.post(_ENDPOINT, json=body, params={"return_offers": "true"})
        resp.raise_for_status()
        offers = (resp.json().get("data", {}) or {}).get("offers", [])
        results: list[FlightOption] = []
        for off in offers[:5]:
            try:
                price = float(off.get("total_amount"))
            except (TypeError, ValueError):
                continue
            carriers = []
            for sl in off.get("slices", []):
                for seg in sl.get("segments", []):
                    mc = (seg.get("marketing_carrier") or {}).get("iata_code")
                    if mc and mc not in carriers:
                        carriers.append(mc)
            results.append(FlightOption(
                origin=origin, destination=alert.destination,
                outbound_date=dep, return_date=ret, return_airport=origin,
                route_type=RouteType.THROUGH, carriers=carriers or ["??"],
                price_eur=price, baggage_included=False, baggage_addon_eur=55.0,
                stay_nights=(ret - dep).days, source=self.name,
                booking_url="https://duffel.com",
            ))
        return results
