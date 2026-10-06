"""Accès sol (train/bus/navette) pour le coût porte-à-porte."""
from __future__ import annotations

from typing import Optional

from ..config import Settings
from ..models import GroundAccess


def ground_access(airport: str, settings: Settings) -> Optional[GroundAccess]:
    home = settings.ground.get("home_city", "Paris")
    key = f"{home}->{airport}"
    opts = settings.ground.get("ground_options", {}) or {}
    entry = opts.get(key) or settings.ground.get("default")
    if not entry:
        return None
    return GroundAccess(
        airport=airport,
        mode=entry.get("mode", "transport"),
        cost_eur=float(entry.get("cost_eur", 0)),
        duration_min=int(entry.get("duration_min", 0)),
    )
