"""Génération de la matrice de dates sur la période."""
from __future__ import annotations

from datetime import date, timedelta

from ..models import Alert


def _walk(start: date, end: date, step: int):
    d = start
    step = max(1, step)
    while d <= end:
        yield d
        d += timedelta(days=step)


def build_date_matrix(alert: Alert) -> list[tuple[date, date]]:
    """Toutes les paires (aller, retour) valides selon la fenêtre et le séjour.

    Trie pour que, à prix égal plus tard, on puisse privilégier le séjour long.
    """
    pairs: list[tuple[date, date]] = []
    start = max(alert.depart_earliest, date.today())  # jamais de date passée
    for dep in _walk(start, alert.depart_latest, alert.date_step_days):
        earliest_ret = max(alert.return_earliest, dep + timedelta(days=alert.stay.min_nights))
        for ret in _walk(earliest_ret, alert.return_latest, alert.date_step_days):
            nights = (ret - dep).days
            if alert.stay.min_nights <= nights <= alert.stay.max_nights:
                pairs.append((dep, ret))
    # séjour le plus long d'abord si maximize
    if alert.stay.maximize:
        pairs.sort(key=lambda p: (p[1] - p[0]).days, reverse=True)
    return pairs
