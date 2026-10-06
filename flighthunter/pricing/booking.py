"""Réservation anticipée : recommande de réserver tôt / au plus bas / d'attendre.

Objectif utilisateur : réserver le plus tôt possible pour payer très peu cher.
On combine deux signaux : (1) le délai avant départ vs une fenêtre optimale,
(2) le prix actuel vs le plus bas historique observé pour ce mois de départ.
"""
from __future__ import annotations

from datetime import date

from ..models import FlightOption


def lead_days(outbound: date) -> int:
    return (outbound - date.today()).days


def recommend(
    opt: FlightOption, prev_min: float | None, lead_window: tuple[int, int]
) -> str:
    parts: list[str] = []
    ld = opt.days_to_departure
    min_d, max_d = lead_window

    if ld is not None:
        if ld < 0:
            parts.append("date passée")
        elif ld > max_d:
            parts.append(f"très anticipé ({ld} j) — surveillez, les tarifs bougent encore")
        elif ld >= min_d:
            parts.append(f"✅ fenêtre optimale ({ld} j avant) — bon moment pour bloquer un prix bas")
        else:
            parts.append(f"⏰ proche du départ ({ld} j) — souvent plus cher, prenez vite si correct")

    if prev_min is not None and opt.net_price_eur is not None:
        if opt.net_price_eur <= prev_min * 1.02:
            parts.append("💰 au plus bas jamais vu sur ce mois → RÉSERVEZ")
        elif opt.net_price_eur <= prev_min * 1.10:
            parts.append(f"proche du plus bas observé ({prev_min:.0f} €)")
        else:
            parts.append(f"au-dessus du plus bas observé ({prev_min:.0f} €) — attente possible")

    return " · ".join(parts)
