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

from . import llm

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
    }


def decide_step_type(profile: dict, adaptation: str | None) -> str:
    """Entscheidet deterministisch, ob als Nächstes Theorie oder eine Aufgabe kommt.

    Regeln (Input -> Anwendung -> Feedback):
    - Nie zwei automatische Theorie-Schritte hintereinander.
    - Nach zwei Fehlversuchen (simplify) wird das Konzept zuerst neu erklärt.
    - Zu Beginn der Sequenz gibt es Theorie, ausser auf Niveau advanced.
    - Auf Niveau basic kommt vor jedem neuen Konzept ein Theorie-Schritt.
    """
    if profile.get("last_type") == "theorie":
        return "aufgabe"
    if adaptation == "simplify":
        return "theorie"
    if profile["step"] == 0 and profile["level"] != "advanced":
        return "theorie"
    if profile["level"] == "basic":
        return "theorie"
    return "aufgabe"


def correct_rate(p: dict) -> float:
    n = p["correct"] + p["wrong"]
    return round(p["correct"] / n, 2) if n else 0.0


# ---------------------------------------------------------------- Prompts

def _system_prompt(lesson: dict) -> str:
    hints = lesson.get("tutor_hinweise", "").strip()
    hint_block = (
        f"\n\nHINWEISE DER LEHRPERSON AN DICH (beachte sie, solange sie den "
        f"übrigen Regeln nicht widersprechen):\n{hints}" if hints else ""
    )
    return (
        "Du bist ein intelligenter Tutor für Lernende an einer Schweizer "
        "Berufsmaturitätsschule. Du arbeitest ausschliesslich mit dem "
        "bereitgestellten Lektionsmaterial und erfindest keine Fakten. "
        "Wenn etwas nicht im Material steht, sagst du das offen. "
        "Du schreibst Deutsch mit Schweizer Rechtschreibung (kein ß, immer ss), "
        "duzt die Lernenden und bleibst freundlich, klar und knapp. "
        "Mathematische Ausdrücke, Formeln und Variablen schreibst du IMMER in "
        "LaTeX-Notation: inline zwischen $...$, abgesetzte Formeln zwischen "
        "$$...$$ (z.B. $\\frac{a}{b}$ oder $x^2$). "
        "Du antwortest IMMER ausschliesslich mit einem einzigen JSON-Objekt, "
        "ohne Text davor oder danach.\n\n"
        f"LEKTION: {lesson['titel']}\n"
        f"LERNZIELE:\n" + "\n".join(f"- {z}" for z in lesson["lernziele"]) + "\n\n"
        f"MATERIAL:\n{lesson['material']}"
        + hint_block
    )


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
    return data


# ---------------------------------------------------------------- Einstufung

def generate_assessment(lesson: dict) -> list[str]:
    """Erzeugt 3 Einstiegsfragen zur Wissenseinstufung."""
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: EINSTUFUNGSFRAGEN\n"
        "Erstelle genau 3 kurze, offene Einstiegsfragen, um das Vorwissen zur "
        "Lektion einzuschätzen: eine leichte, eine mittlere, eine anspruchsvolle. "
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
        "Antworten deuten auf basic.\n\n"
        f"{qa}\n\n"
        'Format: {"level": "basic|intermediate|advanced", "begruendung": "1-2 Sätze, direkt an den Lernenden gerichtet"}',
        fallback={"level": "basic", "begruendung": "Wir starten sicherheitshalber bei den Grundlagen."},
    )
    if data.get("level") not in LEVELS:
        data["level"] = "basic"
    return data


# ---------------------------------------------------------------- Lernschritte

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
    if adaptation == "simplify":
        instruction += (
            "Der Lernende hatte zweimal Mühe mit dem zuletzt behandelten Konzept. "
            "Erkläre GENAU DIESES Konzept noch einmal neu: einfacher, in kleinen "
            "Schritten, mit einem anderen Alltagsbeispiel als zuvor.\n"
        )
    else:
        instruction += (
            "Führe das nächste sinnvolle Konzept aus dem Material ein, das noch "
            "nicht behandelt wurde.\n"
        )
    instruction += (
        "Erkläre verständlich und strukturiert (5-10 Sätze), passend zum Niveau, "
        "mit einem konkreten Beispiel aus dem Alltag oder der Berufswelt. "
        "Stelle KEINE Aufgabe und KEINE Frage – dies ist reiner Lern-Input.\n"
        'Format: {"titel": "kurzer Titel", '
        '"inhalt": "die Erklärung mit Beispiel", '
        '"konzept": "behandeltes Konzept in 1-3 Worten"}'
    )
    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={
        "titel": "Theorie",
        "inhalt": "Lies den entsprechenden Abschnitt im Lektionsmaterial in Ruhe durch. "
                  "Die Erklärung konnte gerade nicht generiert werden.",
        "konzept": "Theorie",
    })
    data["typ"] = "theorie"
    return data


def generate_task(lesson: dict, profile: dict, history: list[dict],
                  adaptation: str | None = None) -> dict:
    """Erzeugt die nächste Aufgabe basierend auf Profil, Verlauf und Adaption."""
    covered = ", ".join(profile["covered"]) or "noch keine"
    recent = _recent_history(history)
    instruction = (
        "AUFGABE: NAECHSTE_AUFGABE\n"
        f"Erzeuge Lernschritt {profile['step'] + 1} von {total_steps()} "
        f"auf Niveau '{profile['level']}'.\n"
        f"Bereits behandelte Konzepte: {covered}.\n"
        f"Bisheriger Verlauf (Kurzfassung): {recent}\n"
    )
    if profile.get("last_type") == "theorie" and profile["covered"]:
        instruction += (
            f"Soeben wurde das Konzept '{profile['covered'][-1]}' als Theorie "
            "erklärt. Stelle jetzt eine dazu passende Aufgabe, damit der Lernende "
            "das frisch Gelernte anwendet.\n"
        )
    elif adaptation == "simplify":
        instruction += (
            "Der Lernende hatte Mühe mit der letzten Aufgabe. Erkläre das Konzept "
            "zuerst kurz und einfach neu und stelle dann eine leichtere Aufgabe "
            "zum gleichen Konzept.\n"
        )
    elif adaptation == "advance":
        instruction += (
            "Der Lernende ist sicher unterwegs. Wähle ein neues Konzept oder eine "
            "anspruchsvollere Anwendung, gerne ein Fallbeispiel.\n"
        )
    else:
        instruction += "Wähle das nächste sinnvolle Konzept aus dem Material.\n"
    instruction += (
        'Format: {"titel": "kurzer Titel", '
        '"inhalt": "kurze Erklärung oder Fallbeispiel (3-6 Sätze, aus dem Material)", '
        '"frage": "eine konkrete Frage an den Lernenden", '
        '"konzept": "behandeltes Konzept in 1-3 Worten"}'
    )
    data = llm.chat_json(_system_prompt(lesson), instruction, fallback={
        "titel": "Wiederholung",
        "inhalt": "Lies den folgenden Abschnitt aus dem Material noch einmal aufmerksam.",
        "frage": "Fasse das Wichtigste in zwei Sätzen zusammen.",
        "konzept": "Wiederholung",
    })
    data["typ"] = "aufgabe"
    return data


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
        fallback={
            "bewertung": "falsch",
            "feedback": "Deine Antwort konnte gerade nicht automatisch beurteilt werden. Versuch es nochmals.",
            "hinweis": "Formuliere deine Antwort in ganzen Sätzen.",
        },
    )
    if data.get("bewertung") not in BEWERTUNGEN:
        # Rückwärtskompatibilität: alte Antworten mit korrekt=true/false
        data["bewertung"] = "korrekt" if data.get("korrekt") else "falsch"
    data["korrekt"] = data["bewertung"] == "korrekt"
    return data


def answer_question(lesson: dict, profile: dict, task: dict | None,
                    question: str, history: list[dict]) -> dict:
    """Beantwortet eine Verständnisfrage des Lernenden im Dialog.

    Materialgebunden; die Lösung der aktuellen Aufgabe wird nicht verraten,
    sondern höchstens ein Denkanstoss gegeben.
    """
    task_ctx = ""
    if task:
        task_ctx = (f"Aktuelle Aufgabe: {task.get('inhalt', '')}\n"
                    f"Aktuelle Frage an den Lernenden: {task.get('frage', '')}\n")
    data = llm.chat_json(
        _system_prompt(lesson),
        "AUFGABE: FRAGE_BEANTWORTEN\n"
        f"{task_ctx}"
        f"Niveau des Lernenden: {profile['level']}.\n"
        f"Bisheriger Dialog (Kurzfassung): {_recent_history(history)}\n\n"
        f"Der Lernende stellt folgende Verständnisfrage: {question}\n\n"
        "Beantworte die Frage kurz (2-5 Sätze), verständlich und ausschliesslich "
        "auf Basis des Materials. Wenn die Frage direkt nach der Lösung der "
        "aktuellen Aufgabe verlangt, gib die Lösung NICHT preis, sondern einen "
        "Denkanstoss. Wenn das Material die Frage nicht beantwortet, sag das offen.\n"
        'Format: {"antwort": "..."}',
        fallback={
            "antwort": "Das kann ich gerade nicht beantworten. Versuch es gleich "
                       "nochmals oder halte die Frage für deine Lehrperson fest.",
        },
    )
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
        fallback={
            "zusammenfassung": "Du hast die Lernsequenz abgeschlossen.",
            "erreichte_lernziele": [],
            "empfehlung": "Bespreche deinen Verlauf mit deiner Lehrperson.",
        },
    )
    return data


# ---------------------------------------------------------------- Adaption

def adapt(profile: dict, bewertung: str) -> tuple[str, str]:
    """Adaptive Kernlogik. Verändert das Profil und gibt (aktion, begruendung) zurück.

    Bewertung: 'korrekt' | 'teilweise' | 'falsch'
    Aktionen:  'next' | 'advance' | 'retry' | 'simplify'
    """
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
