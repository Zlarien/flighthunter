"""Persistance SQLite : historique des prix, dédup des alertes, métrique ROI."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "flighthunter.db"


class Store:
    def __init__(self, path: Path = DEFAULT_DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_key TEXT NOT NULL,
                net_price REAL NOT NULL,
                source TEXT,
                captured_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_price_route ON price_history(route_key);

            CREATE TABLE IF NOT EXISTS price_obs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_key TEXT NOT NULL,
                depart_month TEXT NOT NULL,
                net_price REAL NOT NULL,
                lead_days INTEGER,
                observed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_obs ON price_obs(route_key, depart_month);

            CREATE TABLE IF NOT EXISTS alerted (
                signature TEXT PRIMARY KEY,
                net_price REAL NOT NULL,
                alerted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_name TEXT,
                net_price REAL,
                reference_price REAL,
                savings REAL,
                booked_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    # -- historique / anomalies --
    def record_price(self, route_key: str, net_price: float, source: str) -> None:
        self.conn.execute(
            "INSERT INTO price_history(route_key, net_price, source, captured_at) VALUES (?,?,?,?)",
            (route_key, net_price, source, datetime.now().isoformat()),
        )
        self.conn.commit()

    def history_prices(self, route_key: str, limit: int = 500) -> list[float]:
        rows = self.conn.execute(
            "SELECT net_price FROM price_history WHERE route_key=? ORDER BY id DESC LIMIT ?",
            (route_key, limit),
        ).fetchall()
        return [r["net_price"] for r in rows]

    # -- observations pour la réservation anticipée (prix par mois de départ) --
    def record_obs(
        self, route_key: str, depart_month: str, net_price: float, lead_days: int | None
    ) -> None:
        self.conn.execute(
            "INSERT INTO price_obs(route_key, depart_month, net_price, lead_days, observed_at) "
            "VALUES (?,?,?,?,?)",
            (route_key, depart_month, net_price, lead_days, datetime.now().isoformat()),
        )
        self.conn.commit()

    def obs_min(self, route_key: str, depart_month: str) -> float | None:
        row = self.conn.execute(
            "SELECT MIN(net_price) AS m FROM price_obs WHERE route_key=? AND depart_month=?",
            (route_key, depart_month),
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None

    # -- déduplication des alertes --
    def was_alerted(self, signature: str, cooldown_hours: int = 24) -> bool:
        row = self.conn.execute(
            "SELECT alerted_at FROM alerted WHERE signature=?", (signature,)
        ).fetchone()
        if not row:
            return False
        last = datetime.fromisoformat(row["alerted_at"])
        return datetime.now() - last < timedelta(hours=cooldown_hours)

    def mark_alerted(self, signature: str, net_price: float) -> None:
        self.conn.execute(
            "INSERT INTO alerted(signature, net_price, alerted_at) VALUES (?,?,?) "
            "ON CONFLICT(signature) DO UPDATE SET net_price=excluded.net_price, alerted_at=excluded.alerted_at",
            (signature, net_price, datetime.now().isoformat()),
        )
        self.conn.commit()

    # -- ROI --
    def record_roi(
        self, alert_name: str, net_price: float, reference_price: float
    ) -> float:
        savings = round(reference_price - net_price, 2)
        self.conn.execute(
            "INSERT INTO roi(alert_name, net_price, reference_price, savings, booked_at) VALUES (?,?,?,?,?)",
            (alert_name, net_price, reference_price, savings, datetime.now().isoformat()),
        )
        self.conn.commit()
        return savings

    def total_savings(self) -> float:
        row = self.conn.execute("SELECT COALESCE(SUM(savings),0) AS s FROM roi").fetchone()
        return float(row["s"])

    def close(self) -> None:
        self.conn.close()
