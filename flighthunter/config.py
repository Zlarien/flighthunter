"""Chargement de la configuration (YAML + variables d'environnement)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import Alert

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


class Settings:
    """Regroupe config fichiers + secrets d'environnement."""

    def __init__(self, config_dir: Path = CONFIG_DIR) -> None:
        self.config_dir = config_dir
        # Charge secrets.env s'il existe (sinon MODE DEMO)
        env_path = config_dir / "secrets.env"
        if env_path.exists():
            load_dotenv(env_path)

        self.alerts: list[Alert] = self._load_alerts()
        self.routes: dict[str, Any] = self._load_yaml("routes.yaml")
        self.ground: dict[str, Any] = self._load_yaml("ground.yaml")
        self.network: dict[str, Any] = self._load_yaml("network.yaml")
        self.insights: dict[str, Any] = self._load_json("insights.json")

    def _load_json(self, name: str) -> dict[str, Any]:
        path = self.config_dir / name
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh) or {}
        except (json.JSONDecodeError, OSError):
            return {}

    def booking_lead_window(self) -> tuple[int, int]:
        b = self.insights.get("booking_lead_days", {}) if self.insights else {}
        return int(b.get("min", 90)), int(b.get("max", 300))

    def high_season_months(self) -> set[int]:
        return set(self.insights.get("high_season_months", []) if self.insights else [])

    def market_banner(self) -> str:
        if not self.insights:
            return ""
        return str(self.insights.get("real_savings_verdict", "")).strip()

    # -- fichiers --
    def _load_yaml(self, name: str) -> dict[str, Any]:
        path = self.config_dir / name
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _load_alerts(self) -> list[Alert]:
        data = self._load_yaml("alerts.yaml")
        raw = data.get("alerts", []) if isinstance(data, dict) else []
        return [Alert.model_validate(item) for item in raw]

    def enabled_alerts(self) -> list[Alert]:
        return [a for a in self.alerts if a.enabled]

    # -- secrets --
    @staticmethod
    def env(key: str, default: str = "") -> str:
        return os.environ.get(key, default) or default

    def has(self, key: str) -> bool:
        return bool(self.env(key))

    @property
    def demo_mode(self) -> bool:
        """MODE DEMO si aucune source de prix réelle n'est configurée."""
        return not any(
            self.has(k) for k in ("TRAVELPAYOUTS_TOKEN", "DUFFEL_TOKEN", "SCRAPFLY_KEY")
        )
