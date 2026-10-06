"""Envoi d'alertes via un bot Telegram. Sans config → renvoie False."""
from __future__ import annotations

import httpx

from ..config import Settings


def send_telegram(settings: Settings, text: str) -> bool:
    token = settings.env("TELEGRAM_BOT_TOKEN")
    chat_id = settings.env("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[telegram] envoi échoué : {str(exc).replace(token, '***')}")
        return False
