"""Point d'entrée : `python -m flighthunter`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .config import Settings
from .orchestrator import run_all

_LOG = Path(__file__).resolve().parent.parent / "data" / "flighthunter.log"


def _force_utf8() -> None:
    """La console Windows est souvent en cp1252 → on force l'UTF-8 pour les emojis."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


class _Tee:
    """Écrit à la fois sur la console et dans data/flighthunter.log (traçabilité tâche planifiée)."""

    def __init__(self, console, logfile) -> None:
        self.console = console
        self.logfile = logfile

    def write(self, text: str) -> None:
        self.console.write(text)
        try:
            self.logfile.write(text)
        except Exception:  # noqa: BLE001
            pass

    def flush(self) -> None:
        self.console.flush()
        try:
            self.logfile.flush()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    _force_utf8()
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        logfile = _LOG.open("a", encoding="utf-8")
        logfile.write(f"\n\n===== Run {datetime.now().isoformat()} =====\n")
        sys.stdout = _Tee(sys.stdout, logfile)
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(
        prog="flighthunter",
        description="Chasseur de vols multi-sources (mode DEMO sans clé API).",
    )
    parser.add_argument(
        "--config",
        help="Dossier de config alternatif (par défaut ./config)",
        default=None,
    )
    args = parser.parse_args()

    if args.config:
        from pathlib import Path

        settings = Settings(config_dir=Path(args.config))
    else:
        settings = Settings()
    run_all(settings)


if __name__ == "__main__":
    main()
