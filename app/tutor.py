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
              WISSEN_TEXT["allgemeinwissen" if "allgemeinwissen" in e["wissensstufen"] else "material"],
              STRENGE_TEXT[e["bewertungsstrenge"]]]
    return "\n".join(zeilen) + "\n\n"


STRENGE_TEXT = {
    "nachsichtig": "BEWERTUNGSSTRENGE: nachsichtig. Zentrale Elemente sind nur die Kernaussagen. "
                   "Eigene Worte statt Fachbegriffe gelten als korrekt, solange sie sachlich "
                   "stimmen. Sachliche Fehler gelten trotzdem nie als richtig.",
    "ausgewogen": "BEWERTUNGSSTRENGE: ausgewogen. Alle zentralen Elemente müssen vorhanden sein; "
                  "Fachbegriffe verlangst du dort, wo sie für das Verständnis wichtig sind. Nennt "
                  "die Antwort nur einen Oberbegriff, wo ein spezifischer Begriff gefragt ist "
                  "(etwa «Kausalhaftung» statt «Tierhalterhaftung»), ist dieses Element nur "
                  "ungenau. Sachliche Fehler gelten nie als richtig.",
    "streng": "BEWERTUNGSSTRENGE: streng. Die Antwort muss vollständig sein und die korrekten "
              "Fachbegriffe verwenden; ungenaue oder nur umschriebene Begriffe erfüllen ein "
              "Element nicht (Status ungenau, nicht falsch). Sachliche Fehler gelten nie als richtig.",
}


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


MINDESTLAENGE_MATERIAL = 1000


def check_material(lernziele: list[str], material: str) -> dict:
    """D-06: Gleicht das Material mit den Lernzielen ab (Empfehlung für Lehrpersonen).

    Pro Lernziel: Gibt es eine Erklärung, mindestens ein Beispiel und eine
    Begründung? Das Ergebnis verhindert das Speichern nicht.
    """
    ziele = [z.strip() for z in lernziele if z.strip()]
    data = llm.chat_json(
        "Du unterstützt Lehrpersonen an einer Schweizer Berufsmaturitätsschule beim "
        "Prüfen von Lernmaterial für einen KI-Tutor. Du schreibst Deutsch mit Schweizer "
        "Rechtschreibung (kein ß, immer ss). Du antwortest IMMER ausschliesslich mit einem "
        "einzigen JSON-Objekt.",
        "AUFGABE: MATERIAL_PRUEFEN\n"
        "Prüfe für jedes Lernziel, ob das Material dazu (1) eine Erklärung, (2) mindestens "
        "ein konkretes Beispiel und (3) eine Begründung enthält, warum etwas so ist. Beurteile "
        "nur, was wirklich im Material steht, nicht was du selbst weisst. Ein blosses "
        "Aufzählen von Begriffen ist keine Erklärung.\n\n"
        "LERNZIELE:\n" + "\n".join(f"- {z}" for z in ziele) + "\n\n"
        f"MATERIAL:\n{material[:12000]}\n\n"
        'Format: {"ziele": [{"ziel": "Lernziel wörtlich", "erklaerung": true, "beispiel": true, '
        '"begruendung": true, "hinweis": "was fehlt oder ergänzt werden sollte, sonst leer"}], '
        '"gesamt": "1-2 Sätze Gesamteinschätzung"}',
        fallback={"ziele": [], "gesamt": ""},
    )
    ergebnisse = []
    for i, z in enumerate(ziele):
        roh = next((r for r in data.get("ziele") or [] if isinstance(r, dict)
                    and (r.get("ziel") or "").strip() == z), None)
        if roh is None and i < len(data.get("ziele") or []) and isinstance(data["ziele"][i], dict):
            roh = data["ziele"][i]
        roh = roh or {}
        eintrag = {"ziel": z}
        for feld in ("erklaerung", "beispiel", "begruendung"):
            eintrag[feld] = bool(roh.get(feld)) if roh else None
        eintrag["hinweis"] = str(roh.get("hinweis") or "")
        ergebnisse.append(eintrag)
    hinweise = []
    if len(material.strip()) < MINDESTLAENGE_MATERIAL:
        hinweise.append(f"Das Material ist mit {len(material.strip())} Zeichen sehr kurz. Der Tutor "
                        "hat dann kaum eigene Erklärungen und Beispiele zur Verfügung und muss auf "
                        "Allgemeinwissen ausweichen oder bleibt vage.")
    luecken = sum(1 for e in ergebnisse for f in ("erklaerung", "beispiel", "begruendung")
                  if e[f] is False) + len(hinweise)
    return {"ziele": ergebnisse, "gesamt": str(data.get("gesamt") or ""), "hinweise": hinweise,
            "luecken": luecken, "geprueft": not data.get("_fallback"),
            "fehler": data.get("_fehler", "") if data.get("_fallback") else ""}


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
    quellen = didaktik.quellen_der_lektion(lesson)
    if quellen:
        # N-01: Die Quellenliste ist konstant, steht aber im Benutzerteil, damit
        # der Systemprompt für alle Schrittarten gleich bleibt.
        instruction += ("Das Material ist nach Quellen gegliedert («### Quelle: …»). Gib im Feld "
                        "quelle genau den Namen der Quelle an, aus der deine Erklärung stammt: "
                        + ", ".join(quellen) + ".\n")
    instruction += (
        "Erkläre verständlich und strukturiert (4-8 Sätze), passend zum Niveau: was gilt, "
        "und warum bzw. wie es funktioniert. Gib zusätzlich genau ein konkretes Beispiel "
        "aus dem Alltag oder der Berufswelt, mit einem Satz, warum das Konzept dort gilt. "
        "Stelle KEINE Aufgabe und KEINE Frage, dies ist reiner Lern-Input.\n"
        'Format: {"titel": "kurzer Titel", '
        '"inhalt": "die Erklärung ohne das Beispiel", '
        '"beispiel": "das Beispiel mit kurzer Begründung", '
        '"konzept": "behandeltes Konzept in 1-3 Worten"'
        + (', "quelle": "Name der verwendeten Quelle"' if quellen else "") + "}"
    )
    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={},
                         check=lambda d: (didaktik.pruefe_felder(d, ("inhalt", "beispiel"))
                                          or didaktik.thema_verfehlt(
                                              f"{d.get('inhalt', '')} {d.get('beispiel', '')}", lesson)))
    if data.get("_fallback"):
        return theory_fallback(lesson, profile, adaptation, data)
    data["typ"] = "theorie"
    _quelle_setzen(data, lesson)
    return data


def _quelle_setzen(data: dict, lesson: dict) -> None:
    """N-01: Nur eine Quelle, die es in der Lektion gibt, wird angezeigt.

    Eine erfundene oder fehlende Angabe verschwindet; die ursprüngliche Angabe
    bleibt für die Lehrperson unter `quelle_verworfen` im Lernverlauf.
    """
    angabe = data.pop("quelle", None)
    if not didaktik.quellen_der_lektion(lesson):
        return
    geprueft = didaktik.quelle_pruefen(angabe, lesson)
    if geprueft:
        data["quelle"] = geprueft
    elif angabe:
        data["quelle_verworfen"] = str(angabe)[:200]


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
            "dieser Konzepte und setze im Feld konzept genau dessen Namen. Die erwartete Antwort "
            "darf kein Konzept und keinen Fachbegriff verlangen, der noch nicht erklärt wurde.\n"
        )
    instruction += f"Aufgabentyp auf diesem Niveau: {AUFGABENTYP_NACH_NIVEAU.get(level, '')}\n"
    if theorie:
        beispiel = theorie.get("beispiel") or theorie.get("inhalt", "")[:400]
        instruction += (
            f"Beispiel aus der letzten Theorie (NICHT wiederverwenden und NICHT abwandeln; "
            f"erfinde einen neuen Fall mit anderem Ort, anderen Beteiligten und anderem "
            f"Gegenstand): {beispiel}\n"
        )
        verboten = didaktik.fallwoerter(theorie, didaktik.themenwoerter(lesson))
        if verboten:
            instruction += ("Diese Wörter aus dem Beispiel und verwandte Wörter dürfen in deinem "
                            "Fall NICHT vorkommen: " + ", ".join(verboten) + ".\n")
    instruction += (
        "Die Frage darf weder die gesuchten Begriffe noch die anzuwendende Methode oder "
        "Rechenoperation nennen (nicht «Addiere die Brüche …», sondern «Wie viel Mehl "
        "brauchst du noch?»). "
        "Die erwartete Antwort und ihre Schlüsselbegriffe dürfen nicht in der Frage vorkommen "
        "(ausser bei Multiple Choice). Schlüsselbegriffe sind nur Fachbegriffe aus dem Material, "
        "die der Lernende selbst nennen oder anwenden muss (z.B. «Tierhalterhaftung», «Nenner»), "
        "keine Personen, Alltagswörter oder Zahlen aus dem Fall. Sprich den Lernenden mit «du» an.\n"
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
        return (didaktik.pruefe_aufgabe(d, theorie, direkt_nach_theorie, lesson)
                or (unerklaert(d, erklaert, texte) if einfuehrung else None))

    # Drei Versuche statt zwei: Die Evaluation mit qwen3:30b zeigte, dass das
    # Modell ein wiederverwendetes Beispiel oft erst beim zweiten Hinweis ersetzt.
    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={}, check=pruefen,
                         versuche=3)
    if data.get("_fallback"):
        return task_fallback(lesson, profile, adaptation, data)
    if not isinstance(data.get("optionen"), list) or data.get("aufgabentyp") != "multiple_choice":
        data["optionen"] = []
    data["typ"] = "aufgabe"
    return data


def unerklaert(task: dict, erklaert: list[str], texte: str) -> str | None:
    """D-02: Verlangt die Aufgabe ein Konzept oder einen Begriff, der in dieser
    Sequenz noch nicht erklärt wurde?"""
    bekannte = didaktik.staemme(texte)
    konzept_teile = [t for t in didaktik.staemme(task.get("konzept") or "") if len(t) >= 5]
    im_text = bool(konzept_teile) and all(
        any(didaktik.gleicher_stamm(t, b) for b in bekannte) for t in konzept_teile)
    if not konzept_erklaert(task.get("konzept"), erklaert) and not im_text:
        return (f"Das Konzept «{task.get('konzept')}» wurde in dieser Sequenz noch nicht erklärt. "
                "Stelle die Aufgabe zu einem bereits erklärten Konzept.")
    for begriff in task.get("schluesselbegriffe") or []:
        teile = [t for t in didaktik.staemme(str(begriff)) if len(t) >= 5]
        if teile and not all(any(didaktik.gleicher_stamm(t, b) for b in bekannte) for t in teile):
            return (f"Die erwartete Antwort verlangt den Begriff «{begriff}», der noch nicht "
                    "erklärt wurde. Frage nur nach bereits Erklärtem.")
    return None


# Felder, die nur der Server und die Lehrperson sehen (nie die Lernenden):
# Die Musterlösung würde die Aufgabe verraten.
INTERNE_FELDER = ("erwartete_antwort", "schluesselbegriffe", "quelle_verworfen")


def fuer_lernende(task: dict | None) -> dict | None:
    if not task:
        return task
    return {k: v for k, v in task.items() if k not in INTERNE_FELDER}


BEWERTUNGEN = ("korrekt", "teilweise", "falsch")


# D-05: Mit der Standardtemperatur bewertete das Modell dieselbe Antwort je nach
# Durchlauf unterschiedlich. Die Bewertung soll reproduzierbar sein.
BEWERTUNG_TEMPERATUR = float(os.getenv("ITS_BEWERTUNG_TEMPERATUR", "0"))


def evaluate_answer(lesson: dict, profile: dict, task: dict, answer: str,
                    vorher: list[dict] | None = None) -> dict:
    """Bewertet eine Antwort dreistufig und liefert KI-Feedback.

    D-05: Die Bewertung läuft in zwei Schritten. Das Modell bestimmt die
    zentralen Elemente einer vollständigen Antwort und prüft jedes einzeln
    (korrekt, falsch, fehlt). Das Urteil leitet der Code daraus ab
    (didaktik.urteil_aus_elementen). Die Elemente landen im Lernverlauf.

    `vorher` enthält die früheren Versuche zur selben Aufgabe. Eine
    Nachbesserung wird zusammen mit dem ersten Versuch bewertet; zuvor wurde
    sie allein bewertet, sodass eine knappe Ergänzung als falsch galt.

    Kategorien und Feedback-Regeln nach dem Vorbild des LLMTutor-Projekts von
    Swiss Learning Analytics.
    """
    vorher = vorher or []
    optionen = task.get("optionen") or []
    kontext = (f"Aufgabe: {task.get('inhalt', '')}\n"
               f"Frage: {task.get('frage', '')}\n")
    if optionen:
        kontext += "Antwortoptionen: " + " | ".join(
            f"{'ABCDEFGH'[i]}) {o}" for i, o in enumerate(optionen)) + "\n"
    if task.get("erwartete_antwort"):
        kontext += (f"Musterlösung (nur für dich, nie verraten): {task['erwartete_antwort']}\n")
    if task.get("schluesselbegriffe"):
        kontext += "Schlüsselbegriffe der Lösung: " + ", ".join(task["schluesselbegriffe"]) + "\n"
    if vorher:
        for i, v in enumerate(vorher, 1):
            kontext += (f"Versuch {i} des Lernenden: {v.get('antwort', '')}\n"
                        f"Dein Hinweis dazu: {v.get('hinweis', '')}\n")
        kontext += (f"Nachbesserung des Lernenden: {answer}\n"
                    "Bewerte die GESAMTANTWORT aus allen Versuchen zusammen. Eine Nachbesserung "
                    "ergänzt den ersten Versuch; sie muss nicht alles wiederholen.\n\n")
    else:
        kontext += f"Antwort des Lernenden: {answer}\n\n"
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: ANTWORT_BEWERTEN\n"
        + kontext +
        "Gehe in zwei Schritten vor:\n"
        "1. Bestimme 2-4 zentrale Elemente einer vollständigen Antwort. Leite sie aus der "
        "Frage und der Musterlösung ab: nur was die Frage tatsächlich verlangt. Fragt sie "
        "nicht nach einer Begründung oder einem Gesetzesartikel, sind diese kein Element.\n"
        "2. Prüfe für jedes Element den Status:\n"
        "   korrekt = sachlich richtig vorhanden (gemäss der Bewertungsstrenge);\n"
        "   ungenau = sachlich zutreffend, aber zu allgemein, nur umschrieben oder ohne den "
        "verlangten Fachbegriff;\n"
        "   falsch = widerspricht der Musterlösung (anderes Ergebnis, anderes Ja/Nein, "
        "vertauschte Bedeutung zweier Begriffe);\n"
        "   fehlt = kommt nicht vor.\n"
        "Kommt die Antwort zu einem anderen Ergebnis als die Musterlösung, setze "
        "sachlicher_widerspruch auf true, auch wenn einzelne Wörter stimmen.\n"
        "Urteil: 'korrekt' = alle Elemente korrekt. 'teilweise' = mindestens ein Element "
        "korrekt oder ungenau und keines falsch. 'falsch' = nichts Zutreffendes oder ein "
        "sachlicher Widerspruch.\n\n"
        "Feedback-Regeln:\n"
        "- Beziehe dich ausdrücklich auf das, was der Lernende geschrieben hat: bestätige die "
        "korrekten Teile und korrigiere genau die fehlenden oder falschen.\n"
        "- korrekt: kurz und präzis bestätigen (max. 1 Satz), dann knapp ergänzen, was "
        "noch dazugehört.\n"
        "- teilweise: benennen, was stimmt und was fehlt; im Hinweis einen Denkanstoss zur "
        "Ergänzung geben, OHNE die Antwort zu verraten.\n"
        "- falsch: knapp erklären, was nicht stimmt, ohne die richtige Antwort zu nennen; im "
        "Hinweis einen gezielten Denkanstoss geben. Keine positiven Floskeln.\n"
        "Formuliere den Hinweis als Anstoss, nicht als neue Frage, die statt der Aufgabe "
        "beantwortet werden soll. Verrate die Lösung nie, auch nicht implizit.\n\n"
        'Format: {"elemente": [{"element": "zentrales Element", "status": "korrekt|ungenau|falsch|fehlt"}], '
        '"sachlicher_widerspruch": false, '
        '"bewertung": "korrekt|teilweise|falsch", '
        '"feedback": "2-4 Sätze direkt an den Lernenden", '
        '"hinweis": "bei teilweise/falsch ein Hinweis für die Nachbesserung, sonst leer"}',
        fallback=dict(FALLBACK_TEXTE["bewertung"]),
        check=lambda d: didaktik.pruefe_felder(d, ("feedback", "hinweis")),
        temperature=BEWERTUNG_TEMPERATUR,
    )
    if data.get("_fallback"):
        # Technischer Fehler: nicht als falsch werten, die Antwort zählt nicht.
        data["bewertung"] = "unbewertet"
        data["korrekt"] = False
        return data
    if data.get("bewertung") not in BEWERTUNGEN:
        # Rückwärtskompatibilität: alte Antworten mit korrekt=true/false
        data["bewertung"] = "korrekt" if data.get("korrekt") else "falsch"
    elemente = [
        {"element": str(e.get("element", "")).strip(), "status": str(e.get("status", "")).strip().lower()}
        for e in (data.get("elemente") or []) if isinstance(e, dict)
    ]
    data["elemente"] = [e for e in elemente if e["status"] in didaktik.ELEMENT_STATUS]
    urteil = didaktik.urteil_aus_elementen(data["elemente"], bool(data.get("sachlicher_widerspruch")))
    if urteil and urteil != data["bewertung"]:
        data["bewertung_modell"] = data["bewertung"]
        data["bewertung"] = urteil
    data["korrekt"] = data["bewertung"] == "korrekt"
    return data


NIVEAU_EINORDNUNG = (
    "Äussert der Lernende einen Wunsch zum Schwierigkeitsniveau (zum Beispiel «Ich möchte "
    "auf dem Grundniveau bleiben» oder «Das ist mir zu schwer»), ordne ihn in niveau_wunsch "
    "und niveau_ziel ein (basic = Grundlagen, intermediate = Fortgeschritten, advanced = "
    "Vertieft). Die Umsetzung und Bestätigung übernimmt das System, bestätige den Wunsch "
    "nicht selbst. Ohne Wunsch: niveau_wunsch keiner, niveau_ziel keins.\n")


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
        + (NIVEAU_EINORDNUNG if art == "frage" else "") +
        'Format: {"antwort": "...", "konzept": "worum es geht, 1-3 Worte", '
        '"ausserhalb_material": false'
        + (', "niveau_wunsch": "keiner|halten|tiefer|hoeher", '
           '"niveau_ziel": "basic|intermediate|advanced|keins"' if art == "frage" else "") + '}',
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
    schritt = {"titel": t["titel"], "inhalt": f"{t['einleitung']}\n\n{abschnitt}",
               "konzept": "", "typ": "theorie", "material_abschnitt": idx,
               "_fallback": True, "_fehler": meta.get("_fehler", "")}
    quelle = didaktik.quelle_fuer_abschnitt(lesson, abschnitt)
    if quelle:
        schritt["quelle"] = quelle
    return schritt


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

SERIE_FUER_NIVEAUFRAGE = 3


def adapt(profile: dict, bewertung: str, kontext: dict | None = None) -> tuple[str, str]:
    """Adaptive Kernlogik. Verändert das Profil und gibt (aktion, begruendung) zurück.

    Bewertung: 'korrekt' | 'teilweise' | 'falsch'
    Aktionen:  'next' | 'retry' | 'simplify' | 'explain'
    kontext:   einsatzart ('einfuehrung' | 'vertiefung'), konzept_erklaert (D-02),
               niveauanpassung ('automatisch' | 'nur_runter' | 'fix') und konzept (D-04)

    Niveausteuerung (D-04):
    - Keine Erhöhung ohne Zustimmung: Nach drei richtigen Antworten in Folge zum
      gleichen Konzept setzt die Logik profile['niveau_frage_offen']; die
      lernende Person entscheidet (siehe niveau_entscheid). Beim Wechsel zu
      einem neuen Konzept beginnt die Zählung neu.
    - Senkung nur um eine Stufe und erst, wenn dieselbe Aufgabe auch im zweiten
      Versuch falsch ist. «Teilweise» und danach «falsch» senkt nicht.
    - «fix» und ein von der lernenden Person festgehaltenes Niveau haben
      Vorrang: dann ändert sich das Niveau automatisch gar nicht.
    """
    k = kontext or {}
    modus = k.get("niveauanpassung", "automatisch")
    fixiert = bool(profile.get("niveau_fixiert"))
    konzept = (k.get("konzept") or "").strip()
    darf_runter = modus in ("automatisch", "nur_runter") and not fixiert
    darf_fragen = modus == "automatisch" and not fixiert
    versuche = profile.setdefault("versuche_aktuell", [])

    if (bewertung == "falsch" and k.get("einsatzart") == "vertiefung"
            and k.get("konzept_erklaert") is False):
        # D-02: In der Vertiefung darf eine Aufgabe Unerklärtes voraussetzen.
        # Eine falsche Antwort dazu führt zu einer Erklärung, nicht zu einer
        # Niveausenkung und nicht zu einem zweiten Versuch ohne Erklärung.
        profile["wrong"] += 1
        _serie_zuruecksetzen(profile)
        profile["attempts_current"] = 0
        versuche.clear()
        profile["step"] += 1
        return "explain", ("Dieses Konzept haben wir noch nicht angeschaut. Ich erkläre es dir "
                           "zuerst, das zählt nicht gegen dein Niveau.")
    if bewertung == "korrekt":
        profile["correct"] += 1
        profile["attempts_current"] = 0
        versuche.clear()
        profile["step"] += 1
        if konzept and profile.get("serie_konzept") == konzept:
            profile["serie"] = profile.get("serie", 0) + 1
        else:
            profile["serie"], profile["serie_konzept"] = 1, konzept
        profile["streak"] = profile["serie"]
        if (profile["serie"] >= SERIE_FUER_NIVEAUFRAGE and darf_fragen
                and profile["level"] != LEVELS[-1]
                and konzept not in profile.get("hoeher_abgelehnt", [])):
            profile["niveau_frage_offen"] = True
        return "next", ""
    if bewertung == "teilweise":
        profile["partial"] = profile.get("partial", 0) + 1
        _serie_zuruecksetzen(profile)
        profile["attempts_current"] += 1
        versuche.append("teilweise")
        if profile["attempts_current"] == 1:
            return "retry", (
                "Da fehlt noch etwas Wichtiges. Schau dir den Hinweis an und "
                "ergänze deine Antwort."
            )
        # Zweite Nachbesserung immer noch unvollständig: akzeptieren und weiter,
        # ohne den Lernenden in einer Schleife festzuhalten.
        profile["attempts_current"] = 0
        versuche.clear()
        profile["correct"] += 1
        profile["step"] += 1
        return "next", (
            "Der Kern stimmt – nimm die Ergänzungen aus dem Feedback mit, "
            "wir gehen weiter."
        )
    # falsch
    profile["wrong"] += 1
    _serie_zuruecksetzen(profile)
    profile["attempts_current"] += 1
    versuche.append("falsch")
    if profile["attempts_current"] == 1:
        return "retry", (
            "Das war noch nicht ganz richtig. Schau dir den Hinweis an und "
            "versuch es gleich nochmals."
        )
    # Zweiter Versuch: vereinfachen, Schritt zählt als bearbeitet. Gesenkt wird
    # nur, wenn beide Versuche falsch waren, und nur um eine Stufe.
    beide_falsch = versuche[-2:] == ["falsch", "falsch"]
    profile["attempts_current"] = 0
    versuche.clear()
    profile["step"] += 1
    reason = "Ich erkläre dir das Konzept nochmals einfacher und stelle dir eine leichtere Aufgabe."
    if beide_falsch and darf_runter:
        von = profile["level"]
        if _level_down(profile):
            profile.setdefault("niveau_verlauf", []).append(
                {"von": von, "nach": profile["level"], "grund": "zweimal falsch bei derselben Aufgabe"})
            reason += f" Wir arbeiten vorerst auf Niveau '{LEVEL_LABELS[profile['level']]}' weiter."
    return "simplify", reason


def _serie_zuruecksetzen(profile: dict):
    profile["serie"] = 0
    profile["streak"] = 0


def niveau_entscheid(profile: dict, aktion: str, level: str | None, modus: str) -> tuple[str, str] | None:
    """Wendet eine Entscheidung der lernenden Person zum Niveau an (D-04).

    aktion: hoeher_ja | hoeher_nein (Antwort auf die Niveaufrage),
            festhalten (mit level: festhalten oder wechseln), automatisch.
    Gibt (neues_level, begründung) zurück oder None, wenn sich nichts ändert.
    """
    von = profile["level"]
    konzept = profile.get("serie_konzept") or ""
    if aktion == "hoeher_ja":
        profile["niveau_frage_offen"] = False
        _serie_zuruecksetzen(profile)
        if modus == "automatisch" and not profile.get("niveau_fixiert") and _level_up(profile):
            return profile["level"], (f"Auf deinen Wunsch geht es jetzt auf Niveau "
                                      f"'{LEVEL_LABELS[profile['level']]}' weiter.")
        return None
    if aktion == "hoeher_nein":
        profile["niveau_frage_offen"] = False
        _serie_zuruecksetzen(profile)
        if konzept:
            profile.setdefault("hoeher_abgelehnt", []).append(konzept)
        return None
    if aktion == "automatisch":
        profile["niveau_fixiert"] = False
        return von, "Das Niveau passt sich wieder automatisch an."
    if aktion == "festhalten":
        ziel = level if level in LEVELS else von
        profile["niveau_fixiert"] = True
        profile["niveau_frage_offen"] = False
        profile["level"] = ziel
        return ziel, f"Das Niveau bleibt auf '{LEVEL_LABELS[ziel]}', bis du es änderst."
    return None


# Einfache, eindeutige Formulierungen werden zusätzlich deterministisch erkannt,
# falls das Modell den Wunsch nicht einordnet.
_WUNSCH_MUSTER = [
    (re.compile(r"(grund(niveau|lagen)|einfachen niveau|basic).{0,40}\b(bleiben|bleibe|lassen)\b|"
                r"\b(bleiben|bleibe)\b.{0,40}(grund(niveau|lagen)|einfachen niveau|basic)", re.I),
     "halten", "basic"),
    (re.compile(r"\b(einfachere|leichtere|einfacher|leichter)e?\s+(aufgaben|fragen)\b|"
                r"\bzu (schwer|schwierig)\b", re.I), "tiefer", None),
    (re.compile(r"\b(schwierigere|anspruchsvollere|schwerere|schwieriger|anspruchsvoller)\s+"
                r"(aufgaben|fragen)\b|\bzu (einfach|leicht)\b", re.I), "hoeher", None),
    (re.compile(r"(einfachst|tiefst|unterst|niedrigst)\w*\s+(level|niveau|stufe)", re.I), "halten", "basic"),
    (re.compile(r"\b(niveau|stufe|level)\b.{0,30}\b(halten|behalten|bleiben|nicht (erhöhen|ändern))\b", re.I),
     "halten", None),
    (re.compile(r"\bnicht (schwieriger|schwerer|anspruchsvoller)\b", re.I), "halten", None),
]


def niveau_wunsch_erkennen(text: str) -> tuple[str, str | None] | None:
    for muster, wunsch, ziel in _WUNSCH_MUSTER:
        if muster.search(text or ""):
            return wunsch, ziel
    return None


def niveau_wunsch_anwenden(profile: dict, wunsch: str, ziel: str | None,
                           modus: str) -> tuple[str | None, str]:
    """Setzt einen im Chat geäusserten Niveauwunsch um. Gibt (neues_level, Bestätigung) zurück."""
    von = profile["level"]
    if modus == "fix":
        return None, (f"Deine Lehrperson hat das Niveau für diese Lektion fest auf "
                      f"'{LEVEL_LABELS[von]}' eingestellt.")
    if ziel in LEVELS:
        profile["level"] = ziel
    elif wunsch == "tiefer":
        _level_down(profile)
    elif wunsch == "hoeher":
        _level_up(profile)
    profile["niveau_fixiert"] = True
    profile["niveau_frage_offen"] = False
    nach = profile["level"]
    if nach == von:
        return nach, (f"Alles klar: Wir bleiben auf dem Niveau «{LEVEL_LABELS[nach]}». "
                      "Du kannst das oben jederzeit ändern.")
    return nach, (f"Alles klar: Wir arbeiten ab jetzt auf dem Niveau «{LEVEL_LABELS[nach]}» "
                  "und bleiben dort. Du kannst das oben jederzeit ändern.")


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
