"""Orchestrateur : radar → normalisation → anomalies → dédup → alerte."""
from __future__ import annotations

from .config import Settings
from .engine.dates import build_date_matrix
from .engine.network import build_extreme
from .models import Alert, FlightOption, RouteType
from .notify.dispatch import format_report, notify
from .pricing.anomaly import is_price_anomaly
from .pricing.booking import lead_days, recommend
from .pricing.normalize import normalize
from .sources import active_sources
from .sources.errorfares import fetch_deals
from .storage.db import Store

RADAR_CAP = 80   # nb max de paires de dates envoyées au "radar" (maîtrise du volume/coût)
TOP_N = 6        # nb d'options présentées dans l'alerte


def _route_key(opt: FlightOption) -> str:
    return f"{opt.origin}-{opt.destination}"


def run_alert(alert: Alert, settings: Settings, store: Store) -> list[FlightOption]:
    """Traite une alerte, envoie une notification si besoin, renvoie le top retenu."""
    date_pairs = build_date_matrix(alert)
    if not date_pairs:
        print(f"[{alert.name}] aucune paire de dates valide — vérifiez la fenêtre/le séjour.")
        return []
    radar = date_pairs[:RADAR_CAP]

    # 1) Collecte multi-sources
    raw: list[FlightOption] = []
    for source in active_sources(settings):
        raw.extend(source.search(alert, radar, settings))

    # 1bis) Chaînes extrêmes (train transfrontalier + vols low-cost + attente hub)
    if alert.techniques.extreme_multileg:
        extreme = build_extreme(alert, settings)
        raw.extend(extreme)
        if extreme:
            print(f"[{alert.name}] {len(extreme)} chaîne(s) extrême(s) générée(s).")

    # 2) Normalisation (filtres + prix net porte-à-porte)
    options = normalize(raw, alert, settings)
    if not options:
        print(f"[{alert.name}] aucune option après filtrage.")
        return []

    # 2bis) Réservation anticipée : délai avant départ + recommandation réserver-tôt
    window = settings.booking_lead_window()
    high_season = settings.high_season_months()
    for opt in options:
        opt.days_to_departure = lead_days(opt.outbound_date)
        month = opt.outbound_date.strftime("%Y-%m")
        rk = _route_key(opt)
        prev_min = store.obs_min(rk, month)
        reco = recommend(opt, prev_min, window)
        if opt.outbound_date.month in high_season:
            reco += " · ⚠️ haute saison (creux en automne, ~-18 %)"
        opt.booking_reco = reco
        if opt.net_price_eur is not None:
            store.record_obs(rk, month, opt.net_price_eur, opt.days_to_departure)

    # 3) Détection d'anomalies AVANT d'enregistrer les prix du run courant
    for opt in options:
        hist = store.history_prices(_route_key(opt))
        if opt.net_price_eur is not None and is_price_anomaly(opt.net_price_eur, hist):
            if not opt.is_error_fare:
                opt.warnings.append("Prix anormalement bas vs historique de la route.")
            opt.is_error_fare = True

    # 4) Historisation
    for opt in options:
        if opt.net_price_eur is not None:
            store.record_price(_route_key(opt), opt.net_price_eur, opt.source)

    # 5) Classement : prix net croissant, puis séjour long d'abord si demandé
    options.sort(
        key=lambda o: (o.net_price_eur or 1e9, -(o.stay_nights or 0) if alert.stay.maximize else 0)
    )

    # 6) Sélection : sous le seuil OU anomalie/erreur de prix
    hits = [
        o for o in options
        if (o.net_price_eur is not None and o.net_price_eur <= alert.max_price_eur) or o.is_error_fare
    ]

    # 7) Déduplication (cooldown 24 h)
    top: list[FlightOption] = []
    for opt in hits:
        if store.was_alerted(opt.signature()):
            continue
        top.append(opt)
        if len(top) >= TOP_N:
            break

    best = options[0]
    if not top:
        print(
            f"[{alert.name}] pas de nouveau deal sous {alert.max_price_eur:.0f} €. "
            f"Meilleur actuel : {best.net_price_eur:.0f} € ({best.origin}→{best.destination}, "
            f"{best.outbound_date})."
        )
        return []

    for opt in top:
        if opt.net_price_eur is not None:
            store.mark_alerted(opt.signature(), opt.net_price_eur)

    # Section dédiée : meilleures chaînes extrêmes (toujours affichée si activées)
    extreme_top = sorted(
        (o for o in options if o.route_type == RouteType.MULTI_LEG),
        key=lambda o: o.net_price_eur or 1e9,
    )[:3]

    deals = fetch_deals(alert) if alert.techniques.error_fares else []

    text = format_report(
        alert, top, settings.demo_mode, store.total_savings(), extreme_top,
        market_banner=settings.market_banner(), deals=deals,
    )
    notify(alert, text, settings)
    return top


def run_all(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    store = Store()
    try:
        alerts = settings.enabled_alerts()
        mode = "DEMO (données simulées)" if settings.demo_mode else "RÉEL"
        print(f"FlightHunter — {len(alerts)} alerte(s) active(s) · mode {mode}\n")
        for alert in alerts:
            run_alert(alert, settings, store)
    finally:
        store.close()
