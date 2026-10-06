"""Interface commune des sources de prix."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..config import Settings
from ..models import Alert, FlightOption


class Source(ABC):
    name: str = "base"

    @abstractmethod
    def search(
        self,
        alert: Alert,
        date_pairs: list[tuple[date, date]],
        settings: Settings,
    ) -> list[FlightOption]:
        """Retourne des options de vol pour l'alerte et les paires de dates."""
        raise NotImplementedError
