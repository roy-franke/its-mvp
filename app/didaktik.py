"""Didaktischer Regelkatalog und deterministische Prüfungen.

Sprachmodelle halten sich nicht zuverlässig an Regeln im Prompt. Wo eine
Regel automatisch prüfbar ist, prüft sie deshalb dieser Code nach der
Generierung; bei einem Verstoss wird einmal mit Korrekturhinweis neu
generiert (siehe llm.chat_json, Parameter `check`) und der Verstoss als
Event protokolliert.

Der Katalog ist bewusst an einer Stelle gebündelt: Prompts beziehen sich
darauf, und eine spätere automatisierte Qualitätsprüfung der Lernverläufe
(Auftrag Kapitel 8) kann dieselben Regeln verwenden.
"""

import re

# ---------------------------------------------------------------- Regelkatalog

REGELN: dict[str, dict] = {
    "T01_KEINE_LEERE_ANKUENDIGUNG": {
        "paket": "T-01",
        "titel": "Keine Ankündigung ohne Inhalt",
        "regel": "Kündige nie etwas an, das nicht unmittelbar im selben Text folgt "
                 "(kein «folgender Abschnitt», «siehe unten», kein Doppelpunkt am Schluss).",
        "pruefbar": True,
    },
}


def regel_text(regel_id: str) -> str:
    return REGELN[regel_id]["regel"]


# ---------------------------------------------------------------- T-01

_SATZENDE = re.compile(r"(?<=[.!?])\s+")
_ANKUENDIGUNG = re.compile(
    r"\b(folgende[nrsm]?|nachfolgende[nrsm]?|im folgenden|untenstehende[nrsm]?|"
    r"(siehe|wie|weiter) unten|unten (genannt|aufgeführt|stehend)e?[nrsm]?)\b",
    re.IGNORECASE,
)


def leere_ankuendigung(text: str) -> str | None:
    """Prüft, ob ein Text etwas ankündigt, das dann fehlt.

    Eine Ankündigung ist nur dann leer, wenn sie am Schluss steht: im letzten
    Satz («Lies den folgenden Abschnitt …») oder als Doppelpunkt am Ende. Steht
    sie weiter vorne («Beachte folgende Punkte: A, B, C.»), folgt der Inhalt ja.
    Gibt eine Beschreibung des Verstosses zurück oder None.
    """
    t = (text or "").strip()
    if not t:
        return None
    if t.endswith(":"):
        return "Der Text endet mit einem Doppelpunkt, aber danach folgt nichts."
    saetze = [s for s in _SATZENDE.split(t) if s.strip()]
    letzter = saetze[-1] if saetze else t
    m = _ANKUENDIGUNG.search(letzter)
    if m:
        return (f"Der Text kündigt mit «{m.group(0)}» etwas an, das nicht folgt. "
                "Schreibe den Inhalt direkt hin, statt ihn anzukündigen.")
    return None


def pruefe_felder(data: dict, felder: tuple[str, ...]) -> str | None:
    """Prüft die sichtbaren Felder eines Schritts gemeinsam auf leere Ankündigungen.

    Die Felder werden in Anzeigereihenfolge zusammengesetzt: Endet der
    Aufgabentext mit «Beantworte die folgende Frage», folgt die Frage ja im
    nächsten Feld und ist damit kein Verstoss.
    """
    text = "\n".join(str(data.get(f) or "") for f in felder).strip()
    return leere_ankuendigung(text)
