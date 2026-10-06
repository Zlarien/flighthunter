"""Sources de prix. Chaque source implémente Source.search()."""
from __future__ import annotations

from ..config import Settings
from .base import Source
from .duffel import DuffelSource
from .mock import MockSource
from .travelpayouts import TravelpayoutsSource


def active_sources(settings: Settings) -> list[Source]:
    """Retourne les sources disponibles selon les clés présentes.

    Sans aucune clé → MODE DEMO (MockSource uniquement).
    """
    sources: list[Source] = []
    if settings.has("TRAVELPAYOUTS_TOKEN"):
        sources.append(TravelpayoutsSource(settings.env("TRAVELPAYOUTS_TOKEN")))
    if settings.has("DUFFEL_TOKEN"):
        sources.append(DuffelSource(settings.env("DUFFEL_TOKEN")))
    if not sources:
        sources.append(MockSource())
    return sources
