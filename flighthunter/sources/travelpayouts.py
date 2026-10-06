"""Source réelle Travelpayouts / Aviasales (données de cache, gratuites).

Deux endpoints combinés :
- v1/prices/cheap        : allers-retours cachés les moins chers (a des données Comores)
- v3/prices_for_dates    : par mois de départ (complément, souvent vide pour HAH)

Défensive : toute erreur réseau renvoie [] sans casser le pipeline.
Docs : https://support.travelpayouts.com/hc/en-us/articles/203956163
"""
from __future__ import annotations

from datetime import date

import httpx

from ..config import Settings
from ..models import Alert, FlightOption, RouteType
from .base import Source

_CHEAP = "https://api.travelpayouts.com/v1/prices/cheap"
_PFD = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _ddmm(d: date) -> str:
    return d.strftime("%d%m")


class TravelpayoutsSource(Source):
    name = "travelpayouts"

    def __init__(self, token: str) -> None:
        self.token = token

    def search(
        self,
        alert: Alert,
        date_pairs: list[tuple[date, date]],
        settings: Settings,
    ) -> list[FlightOption]:
        excluded_carriers = set(settings.routes.get("excluded_carriers", []))
        months = sorted({dep.strftime("%Y-%m") for dep, _ in date_pairs})
        out: list[FlightOption] = []
        try:
            with httpx.Client(timeout=25) as client:
                for origin in alert.origins:
                    out.extend(self._cheap(client, alert, origin, excluded_carriers))
                    for month in months[:4]:  # complément v3 (borne pour le volume)
                        out.extend(self._v3(client, alert, origin, month, excluded_carriers))
        except Exception as exc:  # noqa: BLE001
            print(f"[travelpayouts] requête échouée, ignorée : {exc}")
        return out

    # ---- v1/prices/cheap : allers-retours cachés ----
    def _cheap(
        self, client: httpx.Client, alert: Alert, origin: str, excluded: set[str]
    ) -> list[FlightOption]:
        params = {
            "origin": origin,
            "destination": alert.destination,
            "currency": alert.currency.lower(),
            "token": self.token,
        }
        resp = client.get(_CHEAP, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not (isinstance(payload, dict) and payload.get("success")):
            return []
        results: list[FlightOption] = []
        for _dest, entries in (payload.get("data") or {}).items():
            for row in entries.values():
                opt = self._row_to_option(alert, origin, row, excluded)
                if opt:
                    results.append(opt)
        return results

    # ---- v3/prices_for_dates : complément par mois ----
    def _v3(
        self, client: httpx.Client, alert: Alert, origin: str, month: str, excluded: set[str]
    ) -> list[FlightOption]:
        params = {
            "origin": origin,
            "destination": alert.destination,
            "departure_at": month,
            "currency": alert.currency.lower(),
            "token": self.token,
            "limit": 20,
            "sorting": "price",
            "one_way": "false",
        }
        resp = client.get(_PFD, params=params)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        results: list[FlightOption] = []
        for row in rows:
            opt = self._row_to_option(alert, origin, row, excluded)
            if opt:
                results.append(opt)
        return results

    # ---- normalisation d'une ligne de l'API ----
    def _row_to_option(
        self, alert: Alert, origin: str, row: dict, excluded: set[str]
    ) -> FlightOption | None:
        carrier = str(row.get("airline", "??"))
        if carrier in excluded:
            return None
        dep_raw = row.get("departure_at", "")
        if not dep_raw:
            return None
        try:
            dep = date.fromisoformat(dep_raw[:10])
        except ValueError:
            return None
        ret_raw = row.get("return_at") or ""
        ret = None
        if ret_raw:
            try:
                ret = date.fromisoformat(ret_raw[:10])
            except ValueError:
                ret = None

        warnings: list[str] = []
        if not (alert.depart_earliest <= dep <= alert.depart_latest):
            warnings.append(
                f"Date hors fenêtre stricte ({dep}) — référence de prix réelle du cache."
            )

        url = f"https://www.aviasales.com/search/{origin}{_ddmm(dep)}{alert.destination}"
        if ret:
            url += _ddmm(ret)
        url += "1"

        return FlightOption(
            origin=origin,
            destination=alert.destination,
            outbound_date=dep,
            return_date=ret,
            return_airport=origin,
            route_type=RouteType.THROUGH,
            hubs=[],
            carriers=[carrier],
            price_eur=float(row.get("price", 0)),
            baggage_included=False,
            baggage_addon_eur=55.0,
            stay_nights=(ret - dep).days if ret else None,
            source=self.name,
            booking_url=url,
            warnings=warnings,
        )
