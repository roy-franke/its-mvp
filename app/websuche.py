"""Internetrecherche als dritte Wissensstufe (N-03).

Mit lokalem Ollama hat der Tutor keinen Internetzugang. Die Recherche läuft
deshalb über einen Suchdienst, vorgesehen ist ein selbst betriebenes SearXNG
mit JSON-Ausgabe. Sie ist global abschaltbar und standardmässig aus:

    ITS_WEB_SEARCH=true              schaltet die Recherche ein
    ITS_SEARXNG_URL=http://host:8080 Adresse des SearXNG-Dienstes

Datenschutz: An den Suchdienst geht nur eine fachliche Suchanfrage aus Titel
der Lektion und Konzept. Name, Antworten und Chatnachrichten der lernenden
Person verlassen den Server nie.
"""

from __future__ import annotations

import logging
import os
import re

import httpx

log = logging.getLogger("its.websuche")

TIMEOUT = float(os.getenv("ITS_WEB_SEARCH_TIMEOUT", "8"))


def aktiv() -> bool:
    """Ist die Internetrecherche auf diesem Server eingeschaltet?"""
    an = os.getenv("ITS_WEB_SEARCH", "false").strip().lower() in ("1", "true", "ja", "yes", "on")
    return an and bool(os.getenv("ITS_SEARXNG_URL", "").strip())


def suchanfrage(lesson: dict, konzept: str) -> str:
    """Fachliche Suchanfrage: Konzept und Titel der Lektion, sonst nichts.

    Bewusst ohne Freitext der lernenden Person, damit weder Name noch Antworten
    an einen Dienst ausserhalb gelangen.
    """
    titel = re.sub(r"\(.*?\)", "", lesson.get("titel") or "")
    teile = [konzept or "", titel]
    text = " ".join(t.strip() for t in teile if t and t.strip())
    text = re.sub(r"[^\wÄÖÜäöü .,/-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:160]


def suchen(anfrage: str, anzahl: int = 4) -> list[dict]:
    """Fragt SearXNG ab. Liefert [{titel, url, auszug}], leer bei Fehlern.

    Ist die Recherche ausgeschaltet, findet kein Aufruf nach aussen statt.
    """
    if not aktiv() or not anfrage:
        return []
    base = os.getenv("ITS_SEARXNG_URL", "").rstrip("/")
    try:
        r = httpx.get(f"{base}/search", params={"q": anfrage, "format": "json", "language": "de",
                                                 "safesearch": 1}, timeout=TIMEOUT)
        r.raise_for_status()
        treffer = r.json().get("results") or []
    except Exception as e:           # Suchdienst nicht erreichbar oder falsches Format
        log.warning("Internetrecherche fehlgeschlagen: %s", e)
        return []
    out = []
    for t in treffer:
        url = str(t.get("url") or "")
        if not url.startswith(("http://", "https://")):
            continue
        out.append({"titel": str(t.get("title") or url)[:150], "url": url,
                    "auszug": re.sub(r"\s+", " ", str(t.get("content") or ""))[:500]})
        if len(out) >= anzahl:
            break
    return out
