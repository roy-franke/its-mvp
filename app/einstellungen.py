"""Tutor-Einstellungen pro Lektion (Auftrag Anhang B).

Die Einstellungen stehen im Lektions-JSON unter dem Schlüssel
`einstellungen`. Fehlt ein Wert oder ist er ungültig, gilt der Standard.
Bestehende Lektionen ohne diesen Schlüssel funktionieren damit unverändert.
"""

EINSTELLUNGEN: dict[str, dict] = {
    "einsatzart": {
        "titel": "Einsatzart",
        "werte": {
            "einfuehrung": "Einführung: Der Tutor fragt nur ab, was er vorher erklärt hat",
            "vertiefung": "Vertiefung: Vorwissen aus dem Material darf vorausgesetzt werden",
        },
        "standard": "einfuehrung",
    },
    "niveauanpassung": {
        "titel": "Niveauanpassung",
        "werte": {
            "automatisch": "Automatisch: nach Fehlern tiefer, höher nur mit Zustimmung",
            "nur_runter": "Nur nach unten: bei Schwierigkeiten tiefer, nie automatisch höher",
            "fix": "Fix: Das Niveau bleibt während der ganzen Sequenz gleich",
        },
        "standard": "automatisch",
    },
    "bewertungsstrenge": {
        "titel": "Bewertungsstrenge",
        "werte": {
            "nachsichtig": "Nachsichtig: Kern genügt, eigene Worte statt Fachbegriffe sind in Ordnung",
            "ausgewogen": "Ausgewogen: alle zentralen Elemente, Fachbegriffe wo wichtig",
            "streng": "Streng: vollständig und mit korrekten Fachbegriffen",
        },
        "standard": "ausgewogen",
    },
    "wissensstufen": {
        "titel": "Wissensquellen für Erklärungen",
        "werte": {
            "material": "Lektionsmaterial (immer)",
            "allgemeinwissen": "Allgemeinwissen des Modells, gekennzeichnet",
            "internet": "Internetrecherche mit Quellenlinks, nicht von der Lehrperson geprüft",
        },
        "standard": ["material", "allgemeinwissen"],
        "liste": True,
    },
}


def settings(lesson: dict | None) -> dict:
    """Liefert die gültigen Einstellungen einer Lektion, ergänzt um Standards."""
    roh = (lesson or {}).get("einstellungen") or {}
    out = {}
    for key, d in EINSTELLUNGEN.items():
        wert = roh.get(key)
        if d.get("liste"):
            werte = [w for w in (wert if isinstance(wert, list) else d["standard"]) if w in d["werte"]]
            if "material" not in werte:
                werte.insert(0, "material")      # Das Material gilt immer
            out[key] = werte
        else:
            out[key] = wert if wert in d["werte"] else d["standard"]
    return out


def validate(roh: dict | None) -> dict:
    """Prüft Einstellungen aus dem Editor; unbekannte Werte werfen ValueError."""
    roh = roh or {}
    for key, wert in roh.items():
        d = EINSTELLUNGEN.get(key)
        if d is None:
            raise ValueError(f"Unbekannte Einstellung: {key}")
        if d.get("liste"):
            if not isinstance(wert, list) or any(w not in d["werte"] for w in wert):
                raise ValueError(f"Ungültiger Wert für {d['titel']}")
        elif wert not in d["werte"]:
            raise ValueError(f"Ungültiger Wert für {d['titel']}: {wert}")
    return settings({"einstellungen": roh})


def allgemeinwissen_erlaubt(lesson: dict) -> bool:
    return "allgemeinwissen" in settings(lesson)["wissensstufen"]


def internet_erlaubt(lesson: dict) -> bool:
    """N-03: in der Lektion freigegeben UND auf dem Server eingeschaltet."""
    from . import websuche
    return "internet" in settings(lesson)["wissensstufen"] and websuche.aktiv()
