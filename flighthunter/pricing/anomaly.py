"""Détection d'anomalies de prix (chute statistique vs historique)."""
from __future__ import annotations

import statistics


def is_price_anomaly(net_price: float, history: list[float]) -> bool:
    """Vrai si le prix est anormalement bas par rapport à l'historique de la route.

    Deux critères (il suffit d'un) :
      - < 65 % de la médiane historique ;
      - < moyenne - 2 écarts-types (si assez de données).
    """
    clean = [p for p in history if p and p > 0]
    if len(clean) < 5:
        return False
    median = statistics.median(clean)
    if net_price < 0.65 * median:
        return True
    if len(clean) >= 8:
        mean = statistics.fmean(clean)
        stdev = statistics.pstdev(clean)
        if stdev > 0 and net_price < mean - 2 * stdev:
            return True
    return False
