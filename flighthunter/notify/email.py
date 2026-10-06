"""Envoi d'alertes par e-mail (SMTP). Sans config SMTP → renvoie False."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from ..config import Settings


def send_email(settings: Settings, subject: str, body: str) -> bool:
    host = settings.env("SMTP_HOST")
    user = settings.env("SMTP_USER")
    password = settings.env("SMTP_PASSWORD")
    to_addr = settings.env("SMTP_TO") or user
    from_addr = settings.env("SMTP_FROM") or user
    port = int(settings.env("SMTP_PORT", "587"))
    if not (host and user and password and to_addr):
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[email] envoi échoué : {exc}")
        return False
