"""Moteur de chaînes EXTRÊMES (multi-legs), avec PRIX DE SEGMENTS RÉELS.

domicile --(train transfrontalier)--> porte d'entrée
        --(vols low-cost enchaînés)--> hub (Addis/Nairobi/Istanbul)
        --(attente pour capter le vol régional le moins cher)--> Moroni (HAH)

Chaque segment est prix RÉEL via Travelpayouts si dispo (ex. Paris/Bruxelles→Istanbul
à ~50-90 €), sinon estimation configurée (signalée). Coûts chiffrés honnêtement :
segments, sol, hébergement des nuits d'attente, bagage/segment, coût-risque.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

import httpx

from ..config import Settings
from ..models import Alert, FlightOption, Leg, LegKind, RouteType

_PFD = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


def _pseudo(*parts: object) -> float:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:8], 16) / 0xFFFFFFFF


def _season_adj(d: date) -> float:
    return {6: -30, 7: 130, 8: 110, 9: -20}.get(d.month, 0)


def _synth_price(edge: dict[str, Any], d: date) -> float:
    base = edge.get("base", 300) + _season_adj(d)
    amp = 90 if edge.get("lowcost") else 60
    p = base + amp * _pseudo("fp", edge.get("to"), edge.get("base"), d) - amp / 2
    return max(35.0, round(p, 2))


def _fetch_real_prices(token: str, needed: set[tuple[str, str, str]]) -> dict:
    """Prix RÉELS aller simple les moins chers par (origine, dest, mois)."""
    out: dict[tuple[str, str, str], float] = {}
    capped = list(needed)[:80]  # borne le nombre d'appels
    try:
        with httpx.Client(timeout=20) as client:
            for frm, to, month in capped:
                try:
                    r = client.get(_PFD, params={
                        "origin": frm, "destination": to, "departure_at": month,
                        "currency": "eur", "one_way": "true", "sorting": "price",
                        "limit": 3, "token": token,
                    })
                    rows = r.json().get("data", []) if r.status_code == 200 else []
                    prices = [float(x["price"]) for x in rows if x.get("price")]
                    if prices:
                        out[(frm, to, month)] = min(prices)
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass
    return out


def _leg_price(frm: str, to: str, edge: dict, d: date, real: dict) -> tuple[float, bool]:
    rp = real.get((frm, to, d.strftime("%Y-%m")))
    if rp:
        return round(rp, 2), True
    return _synth_price(edge, d), False


def _sample_dates(alert: Alert, n: int) -> list[date]:
    start = max(alert.depart_earliest, date.today())  # jamais de date passée
    span = (alert.depart_latest - start).days
    if span <= 0 or n <= 1:
        return [start]
    step = max(1, span // (n - 1))
    out: list[date] = []
    d = start
    while d <= alert.depart_latest and len(out) < n:
        out.append(d)
        d += timedelta(days=step)
    return out


def _enum_paths(
    adj: dict[str, list[dict]], node: str, excluded: set[str], final: str,
    max_legs: int, visited: frozenset[str],
) -> list[list[dict]]:
    if max_legs <= 0:
        return []
    paths: list[list[dict]] = []
    for edge in adj.get(node, []):
        to = edge.get("to")
        if to in excluded or to in visited:
            continue
        if to == final:
            paths.append([edge])
        else:
            for sub in _enum_paths(adj, to, excluded, final, max_legs - 1, visited | {to}):
                paths.append([edge] + sub)
    return paths


def build_extreme(alert: Alert, settings: Settings) -> list[FlightOption]:
    cfg = settings.network
    if not cfg or not alert.techniques.extreme_multileg:
        return []

    ex = alert.extreme
    excluded = set(settings.routes.get("excluded_hubs", []))
    adj: dict[str, list[dict]] = cfg.get("flights", {}) or {}
    gw_cfg: dict[str, dict] = cfg.get("ground_gateways", {}) or {}
    notes: dict[str, str] = cfg.get("transit_notes", {}) or {}
    final = cfg.get("final", "HAH")

    gateways = set(alert.origins)
    if ex.allow_cross_border_ground:
        for g, meta in gw_cfg.items():
            if meta.get("cross_border") and adj.get(g):
                gateways.add(g)
    gateways = {g for g in gateways if adj.get(g)}

    dates = _sample_dates(alert, ex.date_samples)

    # Énumère tous les chemins une fois
    paths_by_gw = {gw: _enum_paths(adj, gw, excluded, final, ex.max_flight_legs, frozenset({gw})) for gw in gateways}

    # Collecte les (frm,to,mois) nécessaires et récupère les PRIX RÉELS
    real: dict = {}
    token = settings.env("TRAVELPAYOUTS_TOKEN")
    if token:
        needed: set[tuple[str, str, str]] = set()
        for gw, paths in paths_by_gw.items():
            for path in paths:
                for dep in dates:
                    stay = min(alert.stay.max_nights, (alert.return_latest - dep).days)
                    ret = dep + timedelta(days=stay)
                    node = gw
                    for e in path:
                        needed.add((node, e["to"], dep.strftime("%Y-%m")))
                        needed.add((node, e["to"], ret.strftime("%Y-%m")))
                        node = e["to"]
        real = _fetch_real_prices(token, needed)
        if needed:
            reg = {k for k in needed if k[1] == final}
            reg_real = sum(1 for k in reg if k in real)
            print(
                f"[extreme] segments confirmés réels : {len(real)}/{len(needed)} "
                f"(dont régionaux →{final} : {reg_real}/{len(reg)}). Le reste = estimation signalée."
            )

    results: list[FlightOption] = []
    for gw, paths in paths_by_gw.items():
        for path in paths:
            for dep in dates:
                opt = _assemble(alert, ex, gw, path, dep, gw_cfg, notes, final, real)
                if opt:
                    results.append(opt)

    results.sort(key=lambda o: o.price_eur + o.extra_costs_eur)
    return results[:12]


def _assemble(
    alert: Alert, ex, gw: str, path: list[dict], dep: date,
    gw_cfg: dict, notes: dict, final: str, real: dict,
) -> FlightOption | None:
    max_stay = min(alert.stay.max_nights, (alert.return_latest - dep).days)
    if max_stay < alert.stay.min_nights:
        return None
    stay = max_stay
    ret = dep + timedelta(days=stay)
    if not (alert.return_earliest <= ret <= alert.return_latest):
        return None

    gmeta = gw_cfg.get(gw, {"mode": "transport", "cost_eur": 15, "duration_min": 60})
    ground_out = float(gmeta.get("cost_eur", 15))
    ground_dur = int(gmeta.get("duration_min", 60))

    n_flights = len(path)
    layover_min = int((n_flights - 1) * ex.min_layover_hours * 60)
    transit_min = ground_dur + sum(e.get("dur", 180) for e in path) + layover_min
    if transit_min > ex.max_total_transit_hours * 60:
        return None

    used_estimation = False

    # Vols aller : non-finaux à la date de départ
    out_air = 0.0
    node = gw
    leg_objs: list[Leg] = [
        Leg(kind=LegKind.GROUND, frm="Domicile", to=gw, mode=gmeta.get("mode", "sol"),
            price_eur=ground_out, duration_min=ground_dur)
    ]
    for i, e in enumerate(path[:-1]):
        p, is_real = _leg_price(node, e["to"], e, dep, real)
        used_estimation = used_estimation or not is_real
        out_air += p
        leg_objs.append(Leg(kind=LegKind.FLIGHT, frm=node, to=e["to"],
                            mode=e.get("carrier", "?") + ("" if is_real else " (est.)"),
                            price_eur=p, duration_min=e.get("dur", 180)))
        node = e["to"]

    # Dernier segment régional -> HAH : optimiser l'attente au hub
    final_edge = path[-1]
    pre_hub = final_edge.get("to") if n_flights == 1 else path[-2].get("to")
    best_wait, best_fp, best_total, best_real = 0, None, None, False
    for w in range(ex.hub_wait.min_nights, ex.hub_wait.max_nights + 1):
        fdate = dep + timedelta(days=w)
        fp, is_real = _leg_price(node, final_edge["to"], final_edge, fdate, real)
        total = fp + w * ex.accommodation_eur_per_night
        if best_total is None or total < best_total:
            best_total, best_wait, best_fp, best_real = total, w, fp, is_real
    out_air += best_fp
    used_estimation = used_estimation or not best_real
    accommodation = best_wait * ex.accommodation_eur_per_night
    leg_objs.append(Leg(kind=LegKind.FLIGHT, frm=node, to=final_edge["to"],
                        mode=final_edge.get("carrier", "?") + ("" if best_real else " (est.)"),
                        price_eur=best_fp, duration_min=final_edge.get("dur", 180),
                        wait_nights=best_wait))

    # Retour symétrique estimé par les mêmes hubs
    ret_air = 0.0
    node = gw
    for e in path:
        p, is_real = _leg_price(node, e["to"], e, ret, real)
        used_estimation = used_estimation or not is_real
        ret_air += p
        node = e["to"]
    ground_back = ground_out

    price_air = round(out_air + ret_air, 2)
    extra = round(ground_out + ground_back + accommodation, 2)
    flight_legs_total = n_flights * 2
    baggage_addon = ex.baggage_eur_per_flight_leg * flight_legs_total
    hubs = [e.get("to") for e in path[:-1]]

    warnings: list[str] = [
        f"Chaîne de {n_flights} vol(s) en billets séparés : aucune protection interligne, "
        f"re-check des bagages à chaque escale. Prévoyez de la marge.",
        f"Temps en transit ~{transit_min // 60} h (hors attente).",
        "Retour estimé symétrique par les mêmes hubs (inclus dans le prix).",
        "À réserver segment par segment sur chaque compagnie.",
    ]
    if used_estimation:
        warnings.append("Certains segments sont ESTIMÉS (pas encore dans le cache réel) — à confirmer.")
    if gmeta.get("cross_border"):
        warnings.insert(0, f"Départ depuis l'étranger via {gmeta.get('mode')} ({ground_out:.0f} €).")
    if best_wait > 0:
        warnings.append(
            f"Attente de {best_wait} nuit(s) à {pre_hub} pour capter le vol régional le moins cher "
            f"(+{accommodation:.0f} € d'hébergement) — profitez-en pour visiter."
        )
    for h in hubs + [final]:
        if h in notes:
            warnings.append(f"[{h}] {notes[h]}")

    return FlightOption(
        origin=gw, destination=final, outbound_date=dep, return_date=ret, return_airport=gw,
        route_type=RouteType.MULTI_LEG, hubs=[h for h in hubs if h],
        carriers=[e.get("carrier", "?") for e in path],
        price_eur=price_air, baggage_included=False, baggage_addon_eur=round(baggage_addon, 2),
        legs=leg_objs, extra_costs_eur=extra,
        extra_costs_label=f"sol {ground_out + ground_back:.0f} € + hébergement {accommodation:.0f} €",
        total_transit_min=transit_min, wait_nights=best_wait, stay_nights=stay,
        source="extreme", warnings=warnings,
    )
