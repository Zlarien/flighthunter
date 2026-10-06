"""Flux d'erreurs de prix / deals communautaires (Secret Flying, Fly4Free) via RSS.

Sans clé (keyless). Lit les flux RSS, filtre par mots-clés pertinents pour l'alerte
(destination, ville, région, origines) et renvoie des DealItem. Défensif : toute
erreur réseau/parse est ignorée.
"""
from __future__ import annotations

import re
from xml.etree.ElementTree import ParseError as ET_ParseError

import httpx
from defusedxml.ElementTree import fromstring  # protège contre XXE / billion-laughs
from defusedxml.common import DefusedXmlException

from ..models import Alert, DealItem

_FEEDS = [
    ("Secret Flying", "https://www.secretflying.com/feed/"),
    ("Fly4Free", "https://www.fly4free.com/feed/"),
]

# Mots-clés pertinents pour les Comores / océan Indien / hubs utiles.
# (On évite les noms de compagnies seuls : trop larges → faux positifs.)
_BASE_KEYWORDS = [
    "comor", "moroni", "mayotte", "zanzibar", "tanzani",
    "nairobi", "addis ababa", "indian ocean", "océan indien", "réunion",
]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def fetch_deals(alert: Alert, limit_per_feed: int = 40) -> list[DealItem]:
    keywords = set(_BASE_KEYWORDS)
    keywords.update(o.lower() for o in alert.origins)
    keywords.add(alert.destination.lower())

    deals: list[DealItem] = []
    try:
        with httpx.Client(
            timeout=20, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (FlightHunter/0.1)"},
        ) as client:
            for name, url in _FEEDS:
                try:
                    deals.extend(_parse_feed(client, name, url, keywords, limit_per_feed))
                except Exception as exc:  # noqa: BLE001
                    print(f"[errorfares] {name} ignoré : {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[errorfares] flux indisponibles : {exc}")
    return deals


def _parse_feed(client, name, url, keywords, limit) -> list[DealItem]:
    resp = client.get(url)
    resp.raise_for_status()
    items = _items_xml(resp.content)
    if not items:
        items = _items_regex(resp.text)  # secours si XML mal formé (anti-bot, & non échappé…)

    out: list[DealItem] = []
    for title, link, desc, pub in items:
        haystack = f"{title} {desc}".lower()
        hit = next((k for k in keywords if k and k in haystack), None)
        if hit:
            out.append(DealItem(
                title=title, url=link, source=name, published=pub,
                snippet=desc[:180], matched=hit,
            ))
        if len(out) >= limit:
            break
    return out


def _items_xml(content: bytes) -> list[tuple[str, str, str, str]]:
    try:
        root = fromstring(content)
    except (ET_ParseError, DefusedXmlException, ValueError):
        return []
    items = []
    for item in root.iter("item"):
        items.append((
            (item.findtext("title") or "").strip(),
            (item.findtext("link") or "").strip(),
            _strip_html(item.findtext("description") or ""),
            (item.findtext("pubDate") or "").strip(),
        ))
    return items


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    val = m.group(1)
    val = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", val, flags=re.DOTALL)
    return _strip_html(val)


def _items_regex(text: str) -> list[tuple[str, str, str, str]]:
    """Extraction tolérante des <item> quand le XML n'est pas bien formé."""
    items = []
    for block in re.findall(r"<item[ >].*?</item>", text, re.DOTALL | re.IGNORECASE):
        items.append((_tag(block, "title"), _tag(block, "link"),
                      _tag(block, "description"), _tag(block, "pubDate")))
    return items
