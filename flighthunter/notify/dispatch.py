"""Mise en forme du rapport d'alerte et envoi multi-canal (email/Telegram/console)."""
from __future__ import annotations

from ..config import Settings
from ..models import Alert, FlightOption, RouteType

_RT_LABEL = {
    RouteType.THROUGH: "billet unique",
    RouteType.SELF_TRANSFER: "billets séparés",
    RouteType.POSITIONING: "vol de positionnement",
    RouteType.OPEN_JAW: "open-jaw",
    RouteType.HIDDEN_CITY: "hidden-city",
    RouteType.MULTI_LEG: "chaîne extrême",
}


def _legs_block(opt: FlightOption) -> list[str]:
    """Rendu compact du trajet aller segment par segment (chaînes extrêmes)."""
    lines = ["   Itinéraire aller :"]
    for leg in opt.legs:
        arrow = "🚆" if leg.kind.value == "ground" else "✈️"
        piece = f"      {arrow} {leg.frm}→{leg.to}  {leg.mode}  {leg.price_eur:.0f} €"
        if leg.wait_nights:
            piece += f"  ⏳ attente {leg.wait_nights} nuit(s)"
        lines.append(piece)
    return lines


def format_option(opt: FlightOption, idx: int) -> str:
    net = opt.net_price_eur if opt.net_price_eur is not None else opt.price_eur
    lines = [
        f"{idx}. {net:.0f} € net  —  {opt.origin}→{opt.destination}"
        + (f"→{opt.return_airport}" if opt.return_airport and opt.return_airport != opt.origin else ""),
        f"   {opt.outbound_date}"
        + (f" → {opt.return_date}" if opt.return_date else "")
        + (f"  ({opt.stay_nights} nuits)" if opt.stay_nights else ""),
        f"   {_RT_LABEL.get(opt.route_type, opt.route_type.value)}"
        + (f" via {'/'.join(opt.hubs)}" if opt.hubs else "")
        + (f" · {'/'.join(opt.carriers)}" if opt.carriers else ""),
        f"   billet(s) {opt.price_eur:.0f} €"
        + (" · soute incluse" if opt.baggage_included else f" · soute +{opt.baggage_addon_eur:.0f} €")
        + (f" · cashback -{opt.cashback_eur:.0f} €" if opt.cashback_eur else "")
        + (f" · risque +{opt.risk_cost_eur:.0f} €" if opt.risk_cost_eur else "")
        + (f" · {opt.extra_costs_label}" if opt.extra_costs_eur else "")
        + (f" · sol {opt.ground.mode} +{opt.ground.cost_eur:.0f} €" if opt.ground else ""),
    ]
    if opt.booking_reco:
        lines.append(f"   📅 {opt.booking_reco}")
    if opt.legs:
        lines.extend(_legs_block(opt))
    if opt.total_transit_min:
        lines.append(f"   ⏱️ transit ~{opt.total_transit_min // 60} h")
    if opt.is_error_fare:
        lines.append("   ⚠️ ERREUR DE PRIX probable — foncez, confirmez tout de suite.")
    for w in opt.warnings:
        lines.append(f"   ⚠️ {w}")
    if opt.booking_url:
        lines.append(f"   → {opt.booking_url}")
    return "\n".join(lines)


def format_report(
    alert: Alert,
    options: list[FlightOption],
    demo_mode: bool,
    total_savings: float,
    extreme_options: list[FlightOption] | None = None,
    market_banner: str = "",
    deals: list | None = None,
) -> str:
    header = f"✈️  {alert.name}"
    if demo_mode:
        header += "   [MODE DEMO — données simulées]"
    sub = (
        f"Seuil : {alert.max_price_eur:.0f} € · bagage : {alert.baggage.value} · "
        f"{len(options)} meilleures options"
    )
    banner = f"\n📊 Vérité marché : {market_banner}\n" if market_banner else ""
    body = "\n\n".join(format_option(o, i + 1) for i, o in enumerate(options))
    report = f"{header}\n{sub}\n{banner}\n{body}"

    if extreme_options:
        section = "\n\n".join(format_option(o, i + 1) for i, o in enumerate(extreme_options))
        report += (
            "\n\n" + "─" * 70
            + "\n🔥 CHAÎNES EXTRÊMES (train transfrontalier + vols low-cost + attente au hub)\n\n"
            + section
        )

    if deals:
        items = "\n".join(
            f"  • [{d.source}] {d.title}\n    {d.url}" for d in deals[:8]
        )
        report += (
            "\n\n" + "─" * 70
            + f"\n🔔 DEALS & ERREURS DE PRIX (flux communautaires, {len(deals)} pertinents)\n\n"
            + items
        )

    report += f"\n\nÉconomies cumulées enregistrées : {total_savings:.0f} €"
    return report


def notify(alert: Alert, text: str, settings: Settings) -> None:
    """Envoie sur les canaux activés ; retombe toujours sur la console."""
    from .email import send_email
    from .telegram import send_telegram

    sent = []
    if alert.notify.email and send_email(settings, f"[FlightHunter] {alert.name}", text):
        sent.append("email")
    if alert.notify.telegram and send_telegram(settings, text):
        sent.append("telegram")

    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)
    if sent:
        print(f"[notify] envoyé via : {', '.join(sent)}")
    else:
        print("[notify] aucun canal configuré → affichage console uniquement.")
