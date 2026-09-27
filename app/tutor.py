"""ITS-Kernlogik: Einstufung, Lernendenprofil, adaptiver Lernpfad, Feedback.

Designprinzipien (aus dem Systemkonzept):
- Materialgebunden: Der Tutor arbeitet nur mit dem Lektionsinhalt, nicht mit freiem Wissen.
- Linear-adaptiver Pfad: richtig -> weiter (bei Serie: Level rauf),
  falsch -> Hinweis und zweiter Versuch, nochmals falsch -> Vereinfachung (Level runter).
- Begründbar: Jede Adaption wird protokolliert und dem Lernenden mitgeteilt.
- Vollständig protokolliert: Jeder Schritt landet im Event-Log (store.py).
"""

import json
import os
import re

from . import didaktik, einstellungen, llm

LEVELS = ["basic", "intermediate", "advanced"]

LEVEL_LABELS = {
    "basic": "Grundlagen",
    "intermediate": "Fortgeschritten",
    "advanced": "Vertieft",
}


def total_steps() -> int:
    return int(os.getenv("ITS_TOTAL_STEPS", "8"))


def new_profile() -> dict:
    return {
        "level": "basic",
        "step": 0,
        "correct": 0,
        "wrong": 0,
        "streak": 0,           # aktuelle Serie richtiger Antworten
        "attempts_current": 0,  # Versuche für die aktuelle Aufgabe
        "covered": [],          # behandelte Konzepte
        "current_task": None,
        "last_type": None,      # letzter Schritt-Typ: theorie | aufgabe
        "theory_steps": 0,      # Anzahl erhaltener Theorie-Schritte (für Analyse)
        "partial": 0,           # Anzahl teilweise korrekter Antworten (für Analyse)
        "confidence": [],       # Sicherheitsangaben 1-10 vor der Bewertung
        "erklaert": [],         # in dieser Sequenz per Theorie erklärte Konzepte (D-02)
        "aufgaben_seit_theorie": 0,
    }


def decide_step_type(profile: dict, adaptation: str | None,
                     einsatzart: str = "einfuehrung") -> str:
    """Entscheidet deterministisch, ob als Nächstes Theorie oder eine Aufgabe kommt.

    Regeln (Input -> Anwendung -> Feedback):
    - Nie zwei automatische Theorie-Schritte hintereinander.
    - Nach zwei Fehlversuchen (simplify) oder einer falschen Antwort zu einem
      noch nicht erklärten Konzept (explain) wird zuerst erklärt.
    - Auf Niveau basic kommt vor jedem neuen Konzept ein Theorie-Schritt.
    - Einführung (D-02): Aufgaben nur zu erklärten Konzepten. Zu Beginn gibt es
      deshalb immer Theorie, auch auf advanced, und nach zwei Aufgaben folgt
      der nächste Theorieschritt mit einem neuen Konzept.
    - Vertiefung: Zu Beginn Theorie ausser auf advanced, danach Aufgaben.
    """
    if profile.get("last_type") == "theorie":
        return "aufgabe"
    if adaptation in ("simplify", "explain"):
        return "theorie"
    if einsatzart == "einfuehrung":
        if not profile.get("erklaert") and profile.get("last_type") is None:
            return "theorie"
        if profile["level"] == "basic" or profile.get("aufgaben_seit_theorie", 0) >= 2:
            return "theorie"
        return "aufgabe"
    if profile["step"] == 0 and profile["level"] != "advanced":
        return "theorie"
    if profile["level"] == "basic":
        return "theorie"
    return "aufgabe"


def konzept_erklaert(konzept: str | None, erklaert: list[str]) -> bool:
    """Wurde das Konzept (oder ein Konzept mit gleichem Wortstamm) schon erklärt?"""
    teile = {s for s in didaktik.staemme(konzept or "") if len(s) >= 5}
    if not teile:
        return True          # ohne erkennbares Konzept nicht blockieren
    for e in erklaert:
        andere = didaktik.staemme(e)
        if any(didaktik.gleicher_stamm(t, a) for t in teile for a in andere if len(a) >= 5):
            return True
    return False


def erklaerte_texte(history: list[dict]) -> str:
    """Alles, was in dieser Sequenz erklärt wurde: Theorieschritte und Tutor-Antworten."""
    teile = []
    for ev in history:
        p = ev["payload"]
        if ev["type"] == "task" and p.get("typ") == "theorie":
            teile += [p.get("titel", ""), p.get("inhalt", ""), p.get("beispiel", ""), p.get("konzept", "")]
        elif ev["type"] == "chat_reply":
            teile.append(p.get("antwort", ""))
    return "\n".join(t for t in teile if t)


def correct_rate(p: dict) -> float:
    n = p["correct"] + p["wrong"]
    return round(p["correct"] / n, 2) if n else 0.0


# ---------------------------------------------------------------- Prompts

def _system_prompt(lesson: dict) -> str:
    """Systemprompt: innerhalb einer Lektion für alle Schrittarten identisch.

    Nur so wirkt der Prompt-Cache von Ollama. Alles, was sich von Schritt zu
    Schritt ändert (gezeigte Theorie, erklärte Konzepte, Beispiele), gehört in
    den Benutzerteil der Anfrage. Lektionseinstellungen dürfen hinein, weil sie
    innerhalb einer Lektion konstant sind.
    """
    hints = lesson.get("tutor_hinweise", "").strip()
    hint_block = (
        f"\n\nHINWEISE DER LEHRPERSON AN DICH (beachte sie, solange sie den "
        f"übrigen Regeln nicht widersprechen):\n{hints}" if hints else ""
    )
    return (
        "Du bist ein intelligenter Tutor für Lernende an einer Schweizer "
        "Berufsmaturitätsschule. Grundlage deiner Arbeit ist das bereitgestellte "
        "Lektionsmaterial; du erfindest keine Fakten. "
        "Du schreibst Deutsch mit Schweizer Rechtschreibung (kein ß, immer ss), "
        "duzt die Lernenden und bleibst freundlich, klar und knapp. "
        "Mathematische Ausdrücke, Formeln und Variablen schreibst du IMMER in "
        "LaTeX-Notation: inline zwischen $...$, abgesetzte Formeln zwischen "
        "$$...$$ (z.B. $\\frac{a}{b}$ oder $x^2$). "
        "Du antwortest IMMER ausschliesslich mit einem einzigen JSON-Objekt, "
        "ohne Text davor oder danach.\n\n"
        + didaktik.regeln_fuer_prompt() + "\n\n"
        + _einstellungen_block(lesson)
        + f"LEKTION: {lesson['titel']}\n"
        f"LERNZIELE:\n" + "\n".join(f"- {z}" for z in lesson["lernziele"]) + "\n\n"
        f"MATERIAL:\n{lesson['material']}"
        + hint_block
    )


EINSATZART_TEXT = {
    "einfuehrung": "EINSATZART: Einführung. Die Lernenden bringen kein Vorwissen mit. Bewertete "
                   "Aufgaben beziehen sich nur auf Konzepte, die in dieser Lernsequenz bereits "
                   "erklärt wurden. Setze kein Fachwissen voraus, das nicht allgemein bekannt ist.",
    "vertiefung": "EINSATZART: Vertiefung. Die Lernenden bringen Vorwissen mit. Aufgaben dürfen "
                  "Konzepte aus dem Material voraussetzen, die in dieser Sequenz noch nicht "
                  "erklärt wurden.",
}


def _einstellungen_block(lesson: dict) -> str:
    """Lektionseinstellungen als Anweisungen (konstant innerhalb der Lektion)."""
    e = einstellungen.settings(lesson)
    zeilen = ["EINSTELLUNGEN DIESER LEKTION:", EINSATZART_TEXT[e["einsatzart"]],
              WISSEN_TEXT["allgemeinwissen" if "allgemeinwissen" in e["wissensstufen"] else "material"]]
    return "\n".join(zeilen) + "\n\n"


WISSEN_TEXT = {
    "allgemeinwissen": "WISSENSQUELLEN: Grundlage ist das Lektionsmaterial. Reicht es für eine "
                       "Erklärung oder eine Verständnisfrage nicht aus, darfst du mit gesichertem "
                       "Allgemeinwissen erklären; setze dann ausserhalb_material auf true. Die "
                       "Bewertung von Antworten bleibt immer an das Lektionsmaterial gebunden.",
    "material": "WISSENSQUELLEN: Erkläre nur mit dem Lektionsmaterial. Reicht es nicht, sag das "
                "neutral und empfiehl, die Lehrperson zu fragen.",
}


def suggest_goals(material: str) -> dict:
    """Schlägt aus hochgeladenem Material Titel und Lernziele vor (für Lehrpersonen)."""
    data = llm.chat_json(
        "Du unterstützt Lehrpersonen an einer Schweizer Berufsmaturitätsschule "
        "beim Erstellen von Lektionen. Du schreibst Deutsch mit Schweizer "
        "Rechtschreibung (kein ß, immer ss). Du antwortest IMMER ausschliesslich "
        "mit einem einzigen JSON-Objekt.",
        "AUFGABE: LERNZIELE_VORSCHLAGEN\n"
        "Analysiere das folgende Lernmaterial und schlage einen prägnanten "
        "Lektionstitel sowie 3-5 kompetenzorientierte Lernziele vor "
        "(beobachtbare Verben wie erklären, anwenden, einordnen, begründen).\n\n"
        f"MATERIAL:\n{material[:8000]}\n\n"
        'Format: {"titel": "...", "lernziele": ["...", "..."]}',
        fallback={"titel": "", "lernziele": []},
    )
    return llm.public(data)


# ---------------------------------------------------------------- Einstufung

EINSTUFUNG_EINFUEHRUNG = (
    "Die Lektion ist eine Einführung: Die Einstufung bestimmt nur das Startniveau. "
    "Frage nach Alltagserfahrungen, Vorstellungen und allgemein bekanntem Wissen, "
    "nicht nach Fachbegriffen aus dem Material.\n")


def generate_assessment(lesson: dict) -> list[str]:
    """Erzeugt 3 Einstiegsfragen zur Wissenseinstufung."""
    einfuehrung = einstellungen.settings(lesson)["einsatzart"] == "einfuehrung"
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: EINSTUFUNGSFRAGEN\n"
        "Erstelle genau 3 kurze, offene Einstiegsfragen, um das Vorwissen zur "
        "Lektion einzuschätzen: eine leichte, eine mittlere, eine anspruchsvolle. "
        + (EINSTUFUNG_EINFUEHRUNG if einfuehrung else "") +
        'Format: {"questions": ["...", "...", "..."]}',
        fallback={"questions": lesson.get("einstufungsfragen_fallback", [])},
    )
    qs = data.get("questions") or lesson.get("einstufungsfragen_fallback", [])
    return qs[:3]


def evaluate_assessment(lesson: dict, questions: list[str], answers: list[str]) -> dict:
    """Bewertet die Einstufungsantworten und bestimmt das Startniveau."""
    qa = "\n".join(f"Frage: {q}\nAntwort: {a}" for q, a in zip(questions, answers))
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: EINSTUFUNG_BEWERTEN\n"
        "Beurteile das Vorwissen anhand dieser Antworten und bestimme das "
        "Startniveau: basic, intermediate oder advanced. Leere oder sehr knappe "
        "Antworten deuten auf basic.\n"
        + ("Die Lektion ist eine Einführung: Erwarte keine Fachbegriffe, beurteile "
           "Vorstellungen und Alltagswissen.\n"
           if einstellungen.settings(lesson)["einsatzart"] == "einfuehrung" else "")
        + "\n"
        f"{qa}\n\n"
        'Format: {"level": "basic|intermediate|advanced", "begruendung": "1-2 Sätze, direkt an den Lernenden gerichtet"}',
        fallback=dict(FALLBACK_TEXTE["einstufung"]),
    )
    if data.get("level") not in LEVELS:
        data["level"] = "basic"
    return data


# ---------------------------------------------------------------- Lernschritte

def letzte_theorie(history: list[dict]) -> dict | None:
    """Der zuletzt gezeigte Theorieschritt dieser Sequenz (Payload des Events)."""
    for ev in reversed(history):
        if ev["type"] == "task" and ev["payload"].get("typ") == "theorie":
            return ev["payload"]
    return None


AUFGABENTYP_NACH_NIVEAU = {
    "basic": "Lass das Konzept auf einen einfachen, neuen Fall aus dem Alltag anwenden.",
    "intermediate": "Lass das Konzept auf einen anderen Kontext übertragen, zum Beispiel "
                    "aus der Berufswelt, und die Übertragung kurz begründen.",
    "advanced": "Verlange Begründen, Abwägen oder das Verknüpfen mehrerer Konzepte, "
                "zum Beispiel an einem Fall mit zwei möglichen Lösungen.",
}


def generate_theory(lesson: dict, profile: dict, history: list[dict],
                    adaptation: str | None = None) -> dict:
    """Erzeugt einen Theorie-Schritt: Input ohne Aufgabe und ohne Bewertung."""
    covered = ", ".join(profile["covered"]) or "noch keine"
    recent = _recent_history(history)
    instruction = (
        "AUFGABE: THEORIE_SCHRITT\n"
        f"Der Lernende ist auf Niveau '{profile['level']}'.\n"
        f"Bereits behandelte Konzepte: {covered}.\n"
        f"Bisheriger Verlauf (Kurzfassung): {recent}\n"
    )
    vorher = letzte_theorie(history)
    ziel = (profile.get("current_task") or {}).get("konzept") or ""
    if adaptation == "explain" and ziel:
        instruction += (
            f"Der Lernende hat eine Aufgabe zum Konzept '{ziel}' falsch beantwortet, das in "
            "dieser Sequenz noch nicht erklärt wurde. Erkläre GENAU DIESES Konzept "
            "verständlich von Grund auf.\n"
        )
    elif adaptation == "konzept" and ziel:
        instruction += (
            f"Erkläre das Konzept '{ziel}' aus dem Material. Es wird für die nächste "
            "Aufgabe gebraucht, wurde aber noch nicht erklärt.\n"
        )
    elif adaptation == "simplify":
        instruction += (
            "Der Lernende hatte zweimal Mühe mit dem zuletzt behandelten Konzept. "
            "Erkläre GENAU DIESES Konzept noch einmal neu: einfacher, in kleinen "
            "Schritten, mit einem anderen Alltagsbeispiel als zuvor.\n"
        )
        if vorher and vorher.get("beispiel"):
            instruction += f"Bisheriges Beispiel (nicht wiederverwenden): {vorher['beispiel']}\n"
    else:
        instruction += (
            "Führe das nächste sinnvolle Konzept aus dem Material ein, das noch "
            "nicht behandelt wurde.\n"
        )
    instruction += (
        "Erkläre verständlich und strukturiert (4-8 Sätze), passend zum Niveau: was gilt, "
        "und warum bzw. wie es funktioniert. Gib zusätzlich genau ein konkretes Beispiel "
        "aus dem Alltag oder der Berufswelt, mit einem Satz, warum das Konzept dort gilt. "
        "Stelle KEINE Aufgabe und KEINE Frage, dies ist reiner Lern-Input.\n"
        'Format: {"titel": "kurzer Titel", '
        '"inhalt": "die Erklärung ohne das Beispiel", '
        '"beispiel": "das Beispiel mit kurzer Begründung", '
        '"konzept": "behandeltes Konzept in 1-3 Worten"}'
    )
    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={},
                         check=lambda d: didaktik.pruefe_felder(d, ("inhalt", "beispiel")))
    if data.get("_fallback"):
        return theory_fallback(lesson, profile, adaptation, data)
    data["typ"] = "theorie"
    return data


def generate_task(lesson: dict, profile: dict, history: list[dict],
                  adaptation: str | None = None) -> dict:
    """Erzeugt die nächste Aufgabe basierend auf Profil, Verlauf und Adaption.

    D-01: Die Aufgabe verlangt Eigenleistung. Nach der Generierung prüft
    didaktik.pruefe_aufgabe, ob das Lösungswort in der Frage steht, ob das
    Beispiel der Theorie wiederverwendet wird oder ob die Antwort direkt aus
    der Theorie abschreibbar ist. Bei einem Treffer wird einmal neu generiert.
    """
    covered = ", ".join(profile["covered"]) or "noch keine"
    recent = _recent_history(history)
    level = profile["level"]
    theorie = letzte_theorie(history)
    direkt_nach_theorie = profile.get("last_type") == "theorie"
    instruction = (
        "AUFGABE: NAECHSTE_AUFGABE\n"
        f"Erzeuge Lernschritt {profile['step'] + 1} von {total_steps()} "
        f"auf Niveau '{level}'.\n"
        f"Bereits behandelte Konzepte: {covered}.\n"
        f"Bisheriger Verlauf (Kurzfassung): {recent}\n"
    )
    if direkt_nach_theorie and profile["covered"]:
        instruction += (
            f"Soeben wurde das Konzept '{profile['covered'][-1]}' als Theorie "
            "erklärt. Stelle jetzt eine dazu passende Aufgabe, bei der der Lernende "
            "das frisch Gelernte selbständig anwendet.\n"
        )
    elif adaptation == "simplify":
        instruction += (
            "Der Lernende hatte Mühe mit der letzten Aufgabe. Stelle eine einfachere "
            "Aufgabe zum gleichen Konzept: kleiner und stärker gestützt, etwa ein "
            "Teilschritt, ein vertrauterer Kontext oder eine Denkhilfe in der Frage. "
            "Sie muss aber weiterhin eigenes Denken verlangen und darf nicht nur die "
            "Wiederholung des Textes abfragen.\n"
        )
    elif adaptation == "advance":
        instruction += (
            "Der Lernende ist sicher unterwegs. Wähle ein neues Konzept oder eine "
            "anspruchsvollere Anwendung, gerne ein Fallbeispiel.\n"
        )
    else:
        instruction += "Wähle das nächste sinnvolle Konzept aus dem Material.\n"
    einfuehrung = einstellungen.settings(lesson)["einsatzart"] == "einfuehrung"
    erklaert = profile.get("erklaert") or []
    if einfuehrung:
        instruction += (
            "In dieser Sequenz bereits erklärte Konzepte: "
            + (", ".join(erklaert) or "noch keine") + ". Stelle die Aufgabe NUR zu einem "
            "dieser Konzepte. Die erwartete Antwort darf kein Konzept und keinen Fachbegriff "
            "verlangen, der noch nicht erklärt wurde.\n"
        )
    instruction += f"Aufgabentyp auf diesem Niveau: {AUFGABENTYP_NACH_NIVEAU.get(level, '')}\n"
    if theorie:
        beispiel = theorie.get("beispiel") or theorie.get("inhalt", "")[:400]
        instruction += (
            f"Beispiel aus der letzten Theorie (NICHT wiederverwenden, wähle einen anderen "
            f"Fall mit anderem Kontext und anderen Beteiligten): {beispiel}\n"
        )
    instruction += (
        "Die erwartete Antwort und ihre Schlüsselbegriffe dürfen weder in der Frage "
        "noch im Aufgabentext vorkommen (ausser bei Multiple Choice).\n"
        'Format: {"titel": "kurzer Titel", '
        '"inhalt": "Fallbeschreibung oder Situation (2-5 Sätze), ohne die Lösung", '
        '"frage": "eine konkrete Frage an den Lernenden", '
        '"aufgabentyp": "anwenden|begruenden|vergleichen|vorhersagen|fehler_finden|erklaeren|multiple_choice", '
        '"optionen": ["nur bei multiple_choice, sonst leere Liste"], '
        '"erwartete_antwort": "kurze Musterlösung in 1-2 Sätzen (wird nicht angezeigt)", '
        '"schluesselbegriffe": ["1-4 Begriffe, die eine richtige Antwort enthalten muss"], '
        '"konzept": "behandeltes Konzept in 1-3 Worten"}'
    )
    texte = erklaerte_texte(history)

    def pruefen(d: dict) -> str | None:
        return (didaktik.pruefe_aufgabe(d, theorie, direkt_nach_theorie)
                or (unerklaert(d, erklaert, texte) if einfuehrung else None))

    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={}, check=pruefen)
    if data.get("_fallback"):
        return task_fallback(lesson, profile, adaptation, data)
    if not isinstance(data.get("optionen"), list) or data.get("aufgabentyp") != "multiple_choice":
        data["optionen"] = []
    data["typ"] = "aufgabe"
    return data


def unerklaert(task: dict, erklaert: list[str], texte: str) -> str | None:
    """D-02: Verlangt die Aufgabe ein Konzept oder einen Begriff, der in dieser
    Sequenz noch nicht erklärt wurde?"""
    if not konzept_erklaert(task.get("konzept"), erklaert):
        return (f"Das Konzept «{task.get('konzept')}» wurde in dieser Sequenz noch nicht erklärt. "
                "Stelle die Aufgabe zu einem bereits erklärten Konzept.")
    bekannte = didaktik.staemme(texte)
    for begriff in task.get("schluesselbegriffe") or []:
        teile = [t for t in didaktik.staemme(str(begriff)) if len(t) >= 5]
        if teile and not all(any(didaktik.gleicher_stamm(t, b) for b in bekannte) for t in teile):
            return (f"Die erwartete Antwort verlangt den Begriff «{begriff}», der noch nicht "
                    "erklärt wurde. Frage nur nach bereits Erklärtem.")
    return None


# Felder, die nur der Server und die Lehrperson sehen (nie die Lernenden):
# Die Musterlösung würde die Aufgabe verraten.
INTERNE_FELDER = ("erwartete_antwort", "schluesselbegriffe")


def fuer_lernende(task: dict | None) -> dict | None:
    if not task:
        return task
    return {k: v for k, v in task.items() if k not in INTERNE_FELDER}


BEWERTUNGEN = ("korrekt", "teilweise", "falsch")


def evaluate_answer(lesson: dict, profile: dict, task: dict, answer: str) -> dict:
    """Bewertet eine Antwort dreistufig und liefert KI-Feedback.

    Bewertungskategorien und Feedback-Regeln nach dem Vorbild des
    LLMTutor-Projekts von Swiss Learning Analytics.
    """
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: ANTWORT_BEWERTEN\n"
        f"Aufgabe: {task.get('inhalt', '')}\n"
        f"Frage: {task.get('frage', '')}\n"
        f"Antwort des Lernenden: {answer}\n\n"
        "Bewerte die Antwort mit genau einer dieser Kategorien:\n"
        "- 'korrekt': Der zentrale inhaltliche Kern ist richtig erfasst und das "
        "Grundprinzip verstanden, auch wenn Randdetails fehlen oder kleinere "
        "Ungenauigkeiten vorliegen, die das Verständnis nicht beeinträchtigen.\n"
        "- 'teilweise': Ein wesentlicher, für das Verständnis entscheidender "
        "Aspekt fehlt, oder die Antwort ist fachlich unpräzis oder "
        "missverständlich formuliert.\n"
        "- 'falsch': Der Kern der Antwort ist nicht richtig.\n"
        "Faustregel im Zweifel: Wurde das Prinzip verstanden? Wenn ja -> korrekt.\n\n"
        "Feedback-Regeln:\n"
        "- korrekt: kurz und präzis bestätigen (max. 1 Satz), dann knapp die "
        "wichtigsten fehlenden Aspekte ergänzen.\n"
        "- teilweise: kurz benennen, was unpräzis oder unvollständig ist; im "
        "Hinweis eine Rückfrage oder einen Denkanstoss geben, OHNE die Antwort "
        "zu verraten.\n"
        "- falsch: knapp erklären, was nicht stimmt, ohne die richtige Antwort "
        "zu nennen; im Hinweis einen gezielten sokratischen Denkanstoss geben. "
        "Keine positiven Floskeln.\n"
        "Verrate die Lösung nie, auch nicht implizit.\n\n"
        'Format: {"bewertung": "korrekt|teilweise|falsch", '
        '"feedback": "2-4 Sätze direkt an den Lernenden", '
        '"hinweis": "bei teilweise/falsch ein Hinweis für die Nachbesserung, sonst leer"}',
        fallback=dict(FALLBACK_TEXTE["bewertung"]),
        check=lambda d: didaktik.pruefe_felder(d, ("feedback", "hinweis")),
    )
    if data.get("_fallback"):
        # Technischer Fehler: nicht als falsch werten, die Antwort zählt nicht.
        data["bewertung"] = "unbewertet"
        data["korrekt"] = False
        return data
    if data.get("bewertung") not in BEWERTUNGEN:
        # Rückwärtskompatibilität: alte Antworten mit korrekt=true/false
        data["bewertung"] = "korrekt" if data.get("korrekt") else "falsch"
    data["korrekt"] = data["bewertung"] == "korrekt"
    return data


ESKALATION = {
    ("theorie", 1): "Bring einen NEUEN Zugang zum Konzept: eine andere Erklärung oder ein neues "
                    "Beispiel aus einem anderen Lebensbereich als bisher.",
    ("genauer", 1): "Geh in die Tiefe: Erkläre den Mechanismus, die Gründe oder die einzelnen "
                    "Schritte hinter der Aussage (Warum und Wie), mit einem anderen Beispiel als "
                    "bisher. Formuliere nicht einfach das Bisherige um.",
    ("theorie", 2): "Erkläre das Konzept jetzt mit einer Analogie aus dem Alltag oder Schritt "
                    "für Schritt in kleinen, nummerierten Schritten.",
    ("genauer", 2): "Erkläre das Konzept jetzt mit einer Analogie aus dem Alltag oder Schritt "
                    "für Schritt in kleinen, nummerierten Schritten.",
}


def eskalationsstufe(profile: dict, konzept: str) -> int:
    """Zählt Nachfragen pro Konzept und bestimmt die Stufe (D-03, deterministisch).

    Stufe 1: neuer Zugang bzw. Tiefe mit anderem Beispiel, Stufe 2: Analogie oder
    Schritt für Schritt, Stufe 3: Material ausgeschöpft, mit Angebot.
    """
    zaehler = profile.setdefault("nachfragen", {})
    zaehler[konzept] = zaehler.get(konzept, 0) + 1
    return min(zaehler[konzept], 3)


def ausgeschoepft(lesson: dict, konzept: str) -> dict:
    """Stufe 3: ehrliche Aussage ohne LLM-Aufruf, verbunden mit einem Angebot."""
    k = f"«{konzept}»" if konzept else "diesem Thema"
    if einstellungen.allgemeinwissen_erlaubt(lesson):
        return {"antwort": f"Zu {k} habe ich dir alles gezeigt, was das Lektionsmaterial hergibt. "
                           "Ich kann es dir zusätzlich mit Allgemeinwissen erklären. Das geht "
                           "über das Material hinaus und ist entsprechend markiert.",
                "angebot": "allgemeinwissen"}
    return {"antwort": f"Zu {k} habe ich dir alles gezeigt, was das Lektionsmaterial hergibt. "
                       "Wenn noch etwas unklar ist, frag am besten deine Lehrperson. Du kannst "
                       "die Frage auch hier aufschreiben und später mitnehmen.",
            "angebot": "lehrperson"}


def bisherige_erklaerungen(history: list[dict], konzept: str) -> list[str]:
    """Bereits gezeigte Theorietexte und Tutor-Antworten zum Konzept."""
    out = []
    for ev in history:
        p = ev["payload"]
        if ev["type"] == "task" and p.get("typ") == "theorie" and (
                not konzept or konzept_erklaert(konzept, [p.get("konzept", "")])):
            out.append(" ".join(x for x in (p.get("inhalt"), p.get("beispiel")) if x))
        elif ev["type"] == "chat_reply" and p.get("antwort") and (
                p.get("konzept") in (konzept, None, "")):
            out.append(p["antwort"])
    return [t for t in out if t]


def answer_question(lesson: dict, profile: dict, task: dict | None,
                    question: str, history: list[dict], art: str = "frage",
                    stufe: int | None = None) -> dict:
    """Beantwortet eine Frage des Lernenden im Dialog (unbewertet).

    art: frage (freie Verständnisfrage), theorie («Theorie dazu»),
         genauer («Genauer erklären»), allgemeinwissen (Angebot angenommen).
    Bei theorie/genauer bestimmt `stufe` die Eskalation (D-03). Bereits
    gezeigte Texte zum Konzept gehen im Benutzerteil mit, damit sie nicht
    wiederholt werden; eine Ähnlichkeitsprüfung erzwingt sonst eine
    Neugenerierung. Die Lösung der aktuellen Aufgabe wird nie verraten.
    """
    konzept = (task or {}).get("konzept") or ""
    if art in ("theorie", "genauer") and stufe and stufe >= 3:
        out = ausgeschoepft(lesson, konzept)
        out.update(konzept=konzept, ausserhalb_material=False, stufe=3)
        return out
    bisherige = bisherige_erklaerungen(history, konzept)
    task_ctx = ""
    if task:
        task_ctx = (f"Aktuelles Konzept: {konzept}\n"
                    f"Aktueller Schritt: {task.get('inhalt', '')}\n"
                    + (f"Aktuelle Frage an den Lernenden: {task.get('frage', '')}\n"
                       if task.get("frage") else ""))
    gezeigt = ""
    if bisherige:
        gezeigt = ("Bereits gezeigt (NICHT wiederholen, auch nicht umformuliert):\n"
                   + "\n".join(f"{i + 1}) {t[:700]}" for i, t in enumerate(bisherige[-4:])) + "\n")
    if art in ("theorie", "genauer"):
        auftrag = (f"ESKALATIONSSTUFE: {stufe or 1}\n"
                   f"Der Lernende möchte {'mehr Theorie' if art == 'theorie' else 'eine genauere Erklärung'} "
                   f"zum aktuellen Konzept. {ESKALATION[(art, stufe or 1)]} "
                   "Verrate die Lösung der aktuellen Aufgabe nicht. Nennst du eine Anwendung, "
                   "begründe, warum das Konzept dort gilt. Länge: 3-7 Sätze.\n")
    elif art == "allgemeinwissen":
        auftrag = ("ALLGEMEINWISSEN: Das Lektionsmaterial ist zu diesem Konzept ausgeschöpft, "
                   "der Lernende hat eine Erklärung aus Allgemeinwissen angenommen. Erkläre das "
                   "Konzept mit gesichertem Allgemeinwissen, verständlich und mit einem "
                   "begründeten Beispiel (3-7 Sätze). Setze ausserhalb_material auf true.\n")
    else:
        auftrag = (f"Der Lernende stellt folgende Verständnisfrage: {question}\n"
                   "Beantworte sie kurz (2-5 Sätze) und verständlich. Wenn sie direkt nach der "
                   "Lösung der aktuellen Aufgabe verlangt, gib die Lösung NICHT preis, sondern "
                   "einen Denkanstoss. Ist eine Annahme in der Frage falsch, sag das direkt.\n")
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: FRAGE_BEANTWORTEN\n"
        f"{task_ctx}"
        f"Niveau des Lernenden: {profile['level']}.\n"
        f"Bisheriger Dialog (Kurzfassung): {_recent_history(history)}\n"
        f"{gezeigt}\n{auftrag}"
        'Format: {"antwort": "...", "konzept": "worum es geht, 1-3 Worte", '
        '"ausserhalb_material": false}',
        fallback=dict(FALLBACK_TEXTE["frage"]),
        check=lambda d: (didaktik.pruefe_felder(d, ("antwort",))
                         or didaktik.defensiver_einstieg(d.get("antwort", ""))
                         or (didaktik.zu_aehnlich(d.get("antwort", ""), bisherige)
                             if art in ("theorie", "genauer") else None)),
    )
    data["konzept"] = konzept or data.get("konzept") or ""
    data["ausserhalb_material"] = bool(data.get("ausserhalb_material")) or art == "allgemeinwissen"
    data["stufe"] = stufe if art in ("theorie", "genauer") else None
    data["angebot"] = None
    return data


def generate_summary(lesson: dict, profile: dict, history: list[dict]) -> dict:
    """Erzeugt die Abschlusszusammenfassung mit Lernzielabgleich."""
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: ABSCHLUSS\n"
        f"Der Lernende hat {profile['step']} Schritte bearbeitet, "
        f"{profile['correct']} richtig, {profile['wrong']} falsch, "
        f"Endniveau '{profile['level']}'.\n"
        f"Behandelte Konzepte: {', '.join(profile['covered']) or 'keine'}.\n"
        f"Verlauf: {_recent_history(history, 10)}\n\n"
        "Erstelle eine kurze, motivierende Abschlussbilanz.\n"
        'Format: {"zusammenfassung": "3-5 Sätze", '
        '"erreichte_lernziele": ["..."], '
        '"empfehlung": "1-2 Sätze, was als Nächstes sinnvoll wäre"}',
        fallback=dict(FALLBACK_TEXTE["abschluss"]),
    )
    return data


# ---------------------------------------------------------------- Fallbacks
#
# Greift erst, wenn auch der automatische zweite Versuch gescheitert ist
# (llm.chat_json). Fallbacks müssen für Lernende für sich allein brauchbar
# sein: Statt auf das Material zu verweisen, zeigen sie den passenden
# Abschnitt direkt an. Lässt sich keiner bestimmen, sagt der Tutor offen,
# dass ein technisches Problem besteht, und bietet «Nochmals versuchen» an.
# tests/test_fallbacks.py prüft alle Texte auf leere Ankündigungen.

FALLBACK_TEXTE = {
    "einstufung": {
        "level": "basic",
        "begruendung": "Deine Antworten konnten gerade nicht automatisch ausgewertet "
                       "werden. Wir starten deshalb bei den Grundlagen, und dein Tutor "
                       "passt das Niveau unterwegs an.",
    },
    "bewertung": {
        "bewertung": "unbewertet",
        "feedback": "Deine Antwort konnte wegen eines technischen Problems gerade nicht "
                    "beurteilt werden. Sie zählt nicht als Fehler.",
        "hinweis": "Schick die Antwort einfach nochmals ab.",
    },
    "frage": {
        "antwort": "Das kann ich wegen eines technischen Problems gerade nicht "
                   "beantworten. Versuch es gleich nochmals oder halte die Frage "
                   "für deine Lehrperson fest.",
    },
    "abschluss": {
        "zusammenfassung": "Du hast die Lernsequenz abgeschlossen. Die ausführliche "
                           "Bilanz konnte wegen eines technischen Problems gerade nicht "
                           "erstellt werden.",
        "erreichte_lernziele": [],
        "empfehlung": "Bespreche deinen Verlauf mit deiner Lehrperson.",
    },
    "theorie_material": {
        "titel": "Aus dem Lektionsmaterial",
        "einleitung": "Dein Tutor konnte die Erklärung gerade nicht selbst formulieren. "
                      "Hier ist deshalb der passende Abschnitt direkt aus dem "
                      "Lektionsmaterial.",
    },
    "aufgabe_material": {
        "titel": "Aufgabe zum Lektionsmaterial",
        "einleitung": "Dein Tutor konnte gerade keine neue Aufgabe erzeugen. Arbeite "
                      "deshalb mit diesem Abschnitt aus dem Lektionsmaterial.",
        "frage": "Erkläre mit eigenen Worten, was dieser Abschnitt aussagt, und nenne "
                 "ein eigenes Beispiel, das nicht im Text steht.",
    },
    "technischer_fehler": {
        "titel": "Technisches Problem",
        "inhalt": "Dein Tutor konnte den nächsten Schritt wegen eines technischen "
                  "Problems gerade nicht erzeugen. Klick auf «Nochmals versuchen». "
                  "Wenn es wieder nicht klappt, sag deiner Lehrperson Bescheid.",
    },
}


def material_abschnitte(material: str, min_len: int = 250, max_len: int = 1200) -> list[str]:
    """Zerlegt das Material in lesbare Abschnitte (Absätze, zusammengefasst).

    Quellen-Trenner («### Quelle: …», «---») werden entfernt. Sehr lange
    Absätze werden an Satzgrenzen geteilt, sehr kurze zusammengefasst.
    """
    text = re.sub(r"^###\s*Quelle:.*$", "", material or "", flags=re.MULTILINE)
    text = re.sub(r"^\s*---\s*$", "", text, flags=re.MULTILINE)
    absaetze = [re.sub(r"\s+", " ", a).strip() for a in re.split(r"\n\s*\n", text)]
    absaetze = [a for a in absaetze if len(a) >= 40]
    teile: list[str] = []
    for a in absaetze:
        while len(a) > max_len:
            cut = a.rfind(". ", 0, max_len)
            cut = cut + 1 if cut > min_len else max_len
            teile.append(a[:cut].strip())
            a = a[cut:].strip()
        if a:
            teile.append(a)
    out: list[str] = []
    for t in teile:
        if out and len(out[-1]) < min_len and len(out[-1]) + len(t) <= max_len:
            out[-1] = out[-1] + " " + t
        else:
            out.append(t)
    return out


def _woerter(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüA-ZÄÖÜ]{4,}", (text or "").lower())}


def _passender_abschnitt(lesson: dict, profile: dict, adaptation: str | None) -> tuple[int, str] | None:
    abschnitte = material_abschnitte(lesson.get("material", ""))
    if not abschnitte:
        return None
    gezeigt = set(profile.get("fallback_abschnitte", []))
    if adaptation == "simplify" and profile.get("covered"):
        # Nach Fehlversuchen: der Abschnitt, der am besten zum Konzept passt
        ziel = _woerter(profile["covered"][-1])
        best = max(range(len(abschnitte)),
                   key=lambda i: len(ziel & _woerter(abschnitte[i])))
        if ziel & _woerter(abschnitte[best]):
            return best, abschnitte[best]
    for i, a in enumerate(abschnitte):
        if i not in gezeigt:
            return i, a
    return 0, abschnitte[0]


def _fehler_schritt(meta: dict) -> dict:
    out = dict(FALLBACK_TEXTE["technischer_fehler"])
    out.update({"typ": "fehler", "konzept": "", "wiederholbar": True,
                "_fallback": True, "_fehler": meta.get("_fehler", "")})
    return out


def theory_fallback(lesson: dict, profile: dict, adaptation: str | None, meta: dict) -> dict:
    treffer = _passender_abschnitt(lesson, profile, adaptation)
    if treffer is None:
        return _fehler_schritt(meta)
    idx, abschnitt = treffer
    t = FALLBACK_TEXTE["theorie_material"]
    return {"titel": t["titel"], "inhalt": f"{t['einleitung']}\n\n{abschnitt}",
            "konzept": "", "typ": "theorie", "material_abschnitt": idx,
            "_fallback": True, "_fehler": meta.get("_fehler", "")}


def task_fallback(lesson: dict, profile: dict, adaptation: str | None, meta: dict) -> dict:
    treffer = _passender_abschnitt(lesson, profile, adaptation)
    if treffer is None:
        return _fehler_schritt(meta)
    idx, abschnitt = treffer
    t = FALLBACK_TEXTE["aufgabe_material"]
    return {"titel": t["titel"], "inhalt": f"{t['einleitung']}\n\n{abschnitt}",
            "frage": t["frage"], "konzept": "", "typ": "aufgabe",
            "material_abschnitt": idx,
            "_fallback": True, "_fehler": meta.get("_fehler", "")}


# ---------------------------------------------------------------- Adaption

def adapt(profile: dict, bewertung: str, kontext: dict | None = None) -> tuple[str, str]:
    """Adaptive Kernlogik. Verändert das Profil und gibt (aktion, begruendung) zurück.

    Bewertung: 'korrekt' | 'teilweise' | 'falsch'
    Aktionen:  'next' | 'advance' | 'retry' | 'simplify' | 'explain'
    kontext:   einsatzart ('einfuehrung' | 'vertiefung') und konzept_erklaert
               (wurde das Konzept der Aufgabe in dieser Sequenz schon erklärt?)
    """
    k = kontext or {}
    if (bewertung == "falsch" and k.get("einsatzart") == "vertiefung"
            and k.get("konzept_erklaert") is False):
        # D-02: In der Vertiefung darf eine Aufgabe Unerklärtes voraussetzen.
        # Eine falsche Antwort dazu führt zu einer Erklärung, nicht zu einer
        # Niveausenkung und nicht zu einem zweiten Versuch ohne Erklärung.
        profile["wrong"] += 1
        profile["streak"] = 0
        profile["attempts_current"] = 0
        profile["step"] += 1
        return "explain", ("Dieses Konzept haben wir noch nicht angeschaut. Ich erkläre es dir "
                           "zuerst, das zählt nicht gegen dein Niveau.")
    if bewertung == "korrekt":
        profile["correct"] += 1
        profile["streak"] += 1
        profile["attempts_current"] = 0
        profile["step"] += 1
        if profile["streak"] >= 2 and _level_up(profile):
            profile["streak"] = 0
            return "advance", (
                f"Zwei richtige Antworten in Folge – ich erhöhe das Niveau auf "
                f"'{LEVEL_LABELS[profile['level']]}', damit es für dich anspruchsvoll bleibt."
            )
        return "next", ""
    if bewertung == "teilweise":
        profile["partial"] = profile.get("partial", 0) + 1
        profile["streak"] = 0
        profile["attempts_current"] += 1
        if profile["attempts_current"] == 1:
            return "retry", (
                "Da fehlt noch etwas Wichtiges. Schau dir den Hinweis an und "
                "ergänze deine Antwort."
            )
        # Zweite Nachbesserung immer noch unvollständig: akzeptieren und weiter,
        # ohne den Lernenden in einer Schleife festzuhalten.
        profile["attempts_current"] = 0
        profile["correct"] += 1
        profile["step"] += 1
        return "next", (
            "Der Kern stimmt – nimm die Ergänzungen aus dem Feedback mit, "
            "wir gehen weiter."
        )
    # falsch
    profile["wrong"] += 1
    profile["streak"] = 0
    profile["attempts_current"] += 1
    if profile["attempts_current"] == 1:
        return "retry", (
            "Das war noch nicht ganz richtig. Schau dir den Hinweis an und "
            "versuch es gleich nochmals."
        )
    # Zweiter Fehlversuch: vereinfachen, Level ggf. senken, Schritt zählt als bearbeitet
    profile["attempts_current"] = 0
    profile["step"] += 1
    lowered = _level_down(profile)
    reason = "Ich erkläre dir das Konzept nochmals einfacher und stelle dir eine leichtere Aufgabe."
    if lowered:
        reason += f" Wir arbeiten vorerst auf Niveau '{LEVEL_LABELS[profile['level']]}' weiter."
    return "simplify", reason


def _level_up(p: dict) -> bool:
    i = LEVELS.index(p["level"])
    if i < len(LEVELS) - 1:
        p["level"] = LEVELS[i + 1]
        return True
    return False


def _level_down(p: dict) -> bool:
    i = LEVELS.index(p["level"])
    if i > 0:
        p["level"] = LEVELS[i - 1]
        return True
    return False


def _recent_history(history: list[dict], n: int = 5) -> str:
    items = []
    for ev in history[-n:]:
        if ev["type"] == "task":
            kind = "Theorie" if ev["payload"].get("typ") == "theorie" else "Aufgabe"
            items.append(f"{kind}: {ev['payload'].get('titel', '')}")
        elif ev["type"] == "answer_evaluated":
            ok = "richtig" if ev["payload"].get("korrekt") else "falsch"
            items.append(f"Antwort {ok}")
        elif ev["type"] == "chat_question":
            items.append(f"Verständnisfrage: {ev['payload'].get('frage', '')[:80]}")
        elif ev["type"] == "chat_reply":
            items.append(f"Tutor-Antwort: {ev['payload'].get('antwort', '')[:80]}")
    return "; ".join(items) or "leer"
