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
        "paket": "T-01", "bereich": "allgemein",
        "titel": "Keine Ankündigung ohne Inhalt",
        "regel": "Kündige nie etwas an, das nicht unmittelbar im selben Text folgt "
                 "(kein «folgender Abschnitt», «siehe unten», kein Doppelpunkt am Schluss).",
        "pruefbar": True,
    },
    # ------------------------------------------------------------ D-01 Aufgaben
    "T03_DU": {
        "paket": "T-03", "bereich": "allgemein",
        "titel": "Lernende duzen",
        "regel": "Sprich die Lernenden immer mit «du» an, nie mit «Sie», auch in Aufgaben "
                 "(«Begründe …», nicht «Begründen Sie …»).",
        "pruefbar": True,
    },
    "D01_EIGENLEISTUNG": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Eigenleistung statt Abschreiben",
        "regel": "Jede bewertete Aufgabe verlangt eine eigene Denkleistung: auf einen neuen "
                 "Fall anwenden, begründen, vergleichen, eine Folge vorhersagen, einen Fehler "
                 "in einer Aussage finden oder mit eigenen Worten an einem neuen Beispiel erklären.",
        "pruefbar": False,
    },
    "D01_NICHT_ABSCHREIBBAR": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Antwort nicht abschreibbar",
        "regel": "Stelle keine Frage, deren Antwort als Satz oder Begriff wörtlich im eben "
                 "gezeigten Theorietext steht, und keine reine Definitionsabfrage direkt nach "
                 "der Definition.",
        "pruefbar": True,
    },
    "D01_KEIN_LOESUNGSWORT": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Lösungswort nicht in der Frage",
        "regel": "Die erwartete Antwort und ihre Wortstämme kommen nicht in der Frage vor. "
                 "Ausgenommen sind Multiple-Choice-Aufgaben.",
        "pruefbar": True,
    },
    "D01_NEUER_FALL": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Neuer Fall statt Theorie-Beispiel",
        "regel": "Die Aufgabe verwendet einen neu erfundenen Fall, nicht das Beispiel der Theorie "
                 "und auch keine leichte Abwandlung davon (anderes Alter, anderer Name): anderer "
                 "Ort, andere Beteiligte, anderer Gegenstand. Übernimm auch keine Fälle, die "
                 "wörtlich im Material stehen.",
        "pruefbar": True,
    },
    "D01_EINFACHER_ABER_DENKEN": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Einfacher heisst gestützt, nicht trivial",
        "regel": "Eine einfachere Aufgabe nach Fehlern ist kleiner und stärker gestützt "
                 "(Teilschritt, vertrauterer Kontext oder Denkhilfe in der Frage), verlangt "
                 "aber weiterhin eigenes Denken und keine blosse Wiederholung des Textes.",
        "pruefbar": False,
    },
    "D01_AUFGABENTYP_NACH_NIVEAU": {
        "paket": "D-01", "bereich": "aufgabe",
        "titel": "Aufgabentyp folgt dem Niveau",
        "regel": "Niveau basic: auf einen einfachen, neuen Fall anwenden. Niveau intermediate: "
                 "auf einen anderen Kontext übertragen. Niveau advanced: begründen, abwägen "
                 "und mehrere Konzepte verknüpfen.",
        "pruefbar": False,
    },
    # ------------------------------------------------------------ D-03 Erklärungen
    "D03_NEUER_ZUGANG": {
        "paket": "D-03", "bereich": "erklaerung",
        "titel": "«Theorie dazu» bringt einen neuen Zugang",
        "regel": "Wird Theorie nachgefragt, wiederhole nie den bisherigen Text, sondern bring "
                 "einen neuen Zugang: eine andere Erklärung, ein neues Beispiel oder eine "
                 "Veranschaulichung.",
        "pruefbar": True,
    },
    "D03_TIEFE": {
        "paket": "D-03", "bereich": "erklaerung",
        "titel": "«Genauer erklären» geht in die Tiefe",
        "regel": "Wird eine genauere Erklärung verlangt, erkläre den Mechanismus, die Gründe "
                 "oder die einzelnen Schritte hinter der Aussage (das Warum und Wie), statt das "
                 "Was umzuformulieren.",
        "pruefbar": False,
    },
    "D03_ANWENDUNG_BEGRUENDEN": {
        "paket": "D-03", "bereich": "erklaerung",
        "titel": "Anwendungen immer begründen",
        "regel": "Nennst du ein Anwendungsbeispiel, begründe kurz, warum das Konzept dort gilt "
                 "oder nützt. Ein blosses Aufzählen von Anwendungsfeldern genügt nicht.",
        "pruefbar": False,
    },
    "D03_TON": {
        "paket": "D-03", "bereich": "erklaerung",
        "titel": "Klarer, nicht defensiver Ton",
        "regel": "Sag klar, was stimmt und was nicht; ist eine Annahme der lernenden Person "
                 "falsch, sag es direkt. Fehlt etwas im Material, formuliere neutral und "
                 "hilfreich («Dazu sagt das Lektionsmaterial nichts.») und biete an, wie es "
                 "weitergehen kann. Beginne nie mit «Im Material wird nicht erwähnt, dass …» "
                 "und verweise nicht in jedem Satz auf das Material.",
        "pruefbar": True,
    },
    # ------------------------------------------------------------ D-05 Bewertung
    "D05_ZWEI_SCHRITTE": {
        "paket": "D-05", "bereich": "bewertung",
        "titel": "Bewertung in zwei Schritten",
        "regel": "Bestimme zuerst die zentralen Elemente einer vollständigen Antwort und prüfe "
                 "dann für jedes Element, ob es in der Antwort korrekt, falsch oder gar nicht "
                 "vorkommt. Erst daraus folgt das Urteil.",
        "pruefbar": True,
    },
    "D05_URTEIL": {
        "paket": "D-05", "bereich": "bewertung",
        "titel": "Urteil aus den Elementen",
        "regel": "Richtig heisst: alle zentralen Elemente sind korrekt vorhanden. Teilweise "
                 "richtig heisst: mindestens ein Element ist korrekt und keines widerspricht der "
                 "Lösung. Falsch heisst: kein Element ist korrekt oder die Antwort enthält einen "
                 "sachlichen Widerspruch. Sachliche Fehler gelten nie als richtig.",
        "pruefbar": True,
    },
    "D05_FEEDBACK_BEZUG": {
        "paket": "D-05", "bereich": "bewertung",
        "titel": "Feedback bezieht sich auf die Antwort",
        "regel": "Das Feedback bezieht sich ausdrücklich auf das, was die lernende Person "
                 "geschrieben hat: Es bestätigt die korrekten Teile und korrigiert genau die "
                 "fehlenden oder falschen.",
        "pruefbar": False,
    },
    "D05_MATERIAL": {
        "paket": "D-05", "bereich": "bewertung",
        "titel": "Bewertung bleibt materialgebunden",
        "regel": "Bewertet wird nur anhand des Lektionsmaterials, auch wenn du in Erklärungen "
                 "Allgemeinwissen verwenden darfst.",
        "pruefbar": False,
    },
}


def regel_text(regel_id: str) -> str:
    return REGELN[regel_id]["regel"]


def regeln_fuer_prompt() -> str:
    """Alle Regeln als Block für den Systemprompt (für alle Schritte gleich)."""
    gruppen = {"allgemein": "Allgemein", "aufgabe": "Bewertete Aufgaben",
               "erklaerung": "Erklärungen und Antworten auf Fragen",
               "bewertung": "Bewertung von Antworten", "niveau": "Niveau"}
    zeilen = ["DIDAKTISCHE REGELN (verbindlich):"]
    for key, titel in gruppen.items():
        regeln = [r for r in REGELN.values() if r["bereich"] == key]
        if regeln:
            zeilen.append(f"{titel}:")
            zeilen += [f"- {r['regel']}" for r in regeln]
    return "\n".join(zeilen)


# ---------------------------------------------------------------- Wortvergleich
#
# Bewusst einfach und deterministisch: Kleinschreibung, ß → ss, gängige
# Endungen abschneiden. Zwei Stämme gelten als gleich, wenn einer mit dem
# anderen beginnt (haftet/Haftung, beisst/beissen). Zusammensetzungen werden
# erkannt, wenn ein Stamm von mindestens sechs Zeichen im anderen Wort steckt
# (Tierhalter → Tierhalterhaftung).

STOPWOERTER = set("""
aber alle allem allen aller alles also auch auf aus bei beim bin bis bist dann darf das dass
dein deine deinem deinen deiner dem den denn der des die dies diese diesem diesen dieser dieses
doch dort durch ein eine einem einen einer eines einmal etwas euch euer für gegen gibt habe
haben hast hat hatte hier ihm ihn ihr ihre ihrem ihren ihrer ist jede jedem jeden jeder jedes
jetzt kann kannst keine keinem keinen keiner können könnte mehr mein meine mich mir mit muss
musst nach nicht nichts noch nun nur oder ohne sehr sein seine seinem seinen seiner seit sich
sie sind so soll sollte sondern über um und uns unser unter viel vom von vor war waren warum
was weil welche welchem welchen welcher welches wenn wer werden wie wieder will wird wirst wo
wurde wurden zum zur zwei drei vier beide beiden dabei damit dazu davon daher deshalb also
etwa bitte gerade immer schon wirklich eigentlich einfach genau heute morgen gestern
schwer schwere schweren leicht leichte gross grosse grossen klein kleine kleinen gegenstand
gegenstände gegenstands sache sachen person personen mensch menschen jemand jemandem
angestellte angestellter angestellten mitarbeiter mitarbeitende mitarbeitenden
""".split())

_SUFFIXE = ("ungen", "heiten", "keiten", "ung", "heit", "keit", "ern", "en", "er", "es",
            "em", "et", "st", "e", "n", "s", "t")


def stamm(wort: str) -> str:
    w = wort.lower().replace("ß", "ss")
    for suf in _SUFFIXE:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def woerter(text: str) -> list[str]:
    """Inhaltswörter (ohne Stoppwörter und Zahlen, mindestens vier Zeichen)."""
    return [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", text or "")
            if w.lower().replace("ß", "ss") not in STOPWOERTER]


def staemme(text: str) -> set[str]:
    return {stamm(w) for w in woerter(text)}


def gleicher_stamm(a: str, b: str) -> bool:
    if a == b:
        return True
    kurz, lang = sorted((a, b), key=len)
    if len(kurz) >= 4 and lang.startswith(kurz):
        return True
    return len(kurz) >= 6 and kurz in lang


def _kommt_vor(stamm_a: str, text_staemme: set[str]) -> bool:
    return any(gleicher_stamm(stamm_a, t) for t in text_staemme)


def ueberschneidung(a: str, b: str, ausnahmen: set[str] | None = None) -> tuple[float, set[str]]:
    """Anteil der Inhaltswörter von a, die (als Stamm) auch in b vorkommen."""
    sa = {x for x in staemme(a) if not (ausnahmen and _kommt_vor(x, ausnahmen))}
    sb = staemme(b)
    gemeinsam = {x for x in sa if _kommt_vor(x, sb)}
    return (len(gemeinsam) / len(sa) if sa else 0.0), gemeinsam


# ---------------------------------------------------------------- D-05

ELEMENT_STATUS = ("korrekt", "falsch", "fehlt")


def urteil_aus_elementen(elemente, widerspruch: bool = False) -> str | None:
    """Leitet das Urteil deterministisch aus der Einzelbewertung ab (D-05).

    Gibt None zurück, wenn keine brauchbaren Elemente vorliegen; dann gilt das
    Urteil des Modells.
    """
    if not isinstance(elemente, list):
        return None
    status = [str(e.get("status", "")).strip().lower() for e in elemente if isinstance(e, dict)]
    status = [s for s in status if s in ELEMENT_STATUS]
    if not status:
        return None
    if widerspruch or "falsch" in status:
        return "falsch"
    if all(s == "korrekt" for s in status):
        return "korrekt"
    if "korrekt" in status:
        return "teilweise"
    return "falsch"


# ---------------------------------------------------------------- D-01

def _aufgabentext(task: dict) -> str:
    return f"{task.get('inhalt', '')}\n{task.get('frage', '')}"


def schluesselbegriffe(task: dict) -> list[str]:
    begriffe = [b for b in (task.get("schluesselbegriffe") or []) if isinstance(b, str) and b.strip()]
    erwartet = (task.get("erwartete_antwort") or "").strip()
    if erwartet and len(woerter(erwartet)) <= 3:
        begriffe.append(erwartet)
    return begriffe


def loesungswort_in_aufgabe(task: dict, fachwoerter: set[str] | None = None) -> str | None:
    """Kommt ein Lösungsbegriff (oder sein Wortstamm) in der Frage vor?

    Geprüft wird die Frage, nicht die Fallbeschreibung: Die Fallbeschreibung
    darf Angaben enthalten, mit denen gerechnet oder argumentiert wird.
    Begriffe mit Zahlen (Mengen, Brüche) sind Rechenergebnisse, keine
    Lösungswörter. Mit `fachwoerter` (Stämme aus Material, Lernzielen und
    Titel) zählen nur Fachbegriffe der Lektion; so löst ein vom Modell
    ungeschickt gewählter Alltagsbegriff wie «Betreuerin» keinen Verstoss aus.
    """
    if (task.get("aufgabentyp") or "").lower() in ("multiple_choice", "multiple-choice", "mc"):
        return None
    frage_staemme = staemme(task.get("frage") or "")
    fall_staemme = staemme(task.get("inhalt") or "")
    wurzeln = themenwurzeln
    for begriff in schluesselbegriffe(task):
        if re.search(r"\d", begriff):
            continue
        teile = staemme(begriff)
        if not teile:
            continue
        # Angaben aus der Fallbeschreibung sind gegeben, nicht verraten
        if all(_kommt_vor(t, fall_staemme) for t in teile):
            continue
        # Wörter auf der Themenwurzel der Lektion («Bruchform», «Bruchwert» in
        # einer Bruch-Lektion) sind Formatangaben, keine Lösung
        if fachwoerter is not None and all(any(t.startswith(w) for w in wurzeln(fachwoerter)) for t in teile):
            continue
        if fachwoerter is not None and not all(_kommt_vor(t, fachwoerter) for t in teile):
            continue
        if all(_kommt_vor(t, frage_staemme) for t in teile):
            return (f"Der Lösungsbegriff «{begriff}» oder sein Wortstamm steht bereits in der "
                    "Frage. Formuliere die Frage so, dass die Lernenden den Begriff selbst "
                    "finden müssen.")
    return None


class Fachvokabular(set):
    """Stämme der Fachbegriffe einer Lektion, dazu die Themenwurzeln des Titels."""
    wurzeln: set[str] = set()


def fachvokabular(lesson: dict) -> set[str]:
    """Stämme der Fachbegriffe einer Lektion (Material, Lernziele, Titel)."""
    v = Fachvokabular(staemme(" ".join([lesson.get("titel", ""), " ".join(lesson.get("lernziele", [])),
                                        lesson.get("material", "")])))
    # Themenwurzel: die ersten fünf Buchstaben langer Titelwörter
    # («Bruchbegriff» → «bruch»). Wörter darauf sind Themen-, keine Lösungswörter.
    v.wurzeln = {w.lower()[:5] for w in re.findall(r"[A-Za-zÄÖÜäöü]{7,}", lesson.get("titel", ""))}
    return v


def themenwurzeln(fachwoerter) -> set[str]:
    return getattr(fachwoerter, "wurzeln", set())


def thema_verfehlt(texte: str, lesson: dict, schwelle: float = 0.25) -> str | None:
    """Passt ein erzeugter Text überhaupt zur Lektion?

    Im Evaluationslauf lieferte das Modell in der Bruch-Lektion eine Theorie zur
    Familienhauptshaftung. Ist weniger als ein Viertel der Inhaltswörter im
    Lektionsvokabular zu finden, gilt der Text als themenfremd.
    """
    eigene = staemme(texte)
    if len(eigene) < 8 or len(lesson.get("material", "")) < 1500:
        return None      # zu wenig Material, um das Thema daran zu messen
    vokabular = fachvokabular(lesson)
    anteil = sum(1 for w in eigene if _kommt_vor(w, vokabular)) / len(eigene)
    if anteil < schwelle:
        return (f"Der Text passt nicht zur Lektion «{lesson.get('titel', '')}» (nur "
                f"{round(anteil * 100)} Prozent der Wörter stammen aus dem Lektionsvokabular). "
                "Bleib beim Thema und beim Material dieser Lektion.")
    return None


def themenwoerter(lesson: dict) -> set[str]:
    """Wörter, die in jeder Aufgabe der Lektion vorkommen dürfen (Titel, Lernziele)."""
    return staemme(" ".join([lesson.get("titel", ""), " ".join(lesson.get("lernziele", []))]))


def beispiel_wiederverwendet(task: dict, theorie: dict | None,
                             themen: set[str] | None = None) -> str | None:
    """Nutzt die Aufgabe denselben Fall wie das Beispiel der letzten Theorie?

    Wörter aus Titel und Lernzielen der Lektion (`themen`, etwa «haften»,
    «Schaden», «Bruch») zählen nicht als Gemeinsamkeit, weil sie in jedem Fall
    der Lektion vorkommen.
    """
    if not theorie:
        return None
    ausnahmen = staemme(" ".join([theorie.get("konzept") or "", task.get("konzept") or ""]
                                 + schluesselbegriffe(task))) | (themen or set())
    beispiel = (theorie.get("beispiel") or "").strip()
    if beispiel:
        # Verglichen werden nur die Fallwörter des Beispiels: Wörter, die schon in
        # der Erklärung stehen («Arbeitgeber», «Aufsichtspflicht»), beschreiben das
        # Konzept und dürfen in jeder Aufgabe dazu vorkommen.
        ausnahmen = ausnahmen | staemme(theorie.get("inhalt") or "")
        anteil, gemeinsam = ueberschneidung(beispiel, _aufgabentext(task), ausnahmen)
        treffer = len(gemeinsam) >= 3 and anteil >= 0.3
    else:
        # Ältere Theorieschritte ohne eigenes Beispielfeld: Wie viel der
        # Aufgabe besteht aus Wörtern der Theorie?
        anteil, gemeinsam = ueberschneidung(_aufgabentext(task), theorie.get("inhalt", ""), ausnahmen)
        treffer = len(gemeinsam) >= 4 and anteil >= 0.5
    if treffer:
        return ("Die Aufgabe verwendet das Beispiel aus der Theorie wieder (gemeinsam: "
                + ", ".join(sorted(gemeinsam)) + "). Wähle einen anderen Fall mit anderem "
                "Kontext und anderen Beteiligten.")
    return None


_DEFINITIONSFRAGE = re.compile(
    r"^\W*(was (ist|sind|bedeutet|bedeuten|heisst|versteht man unter|meint man mit)|"
    r"definiere|wie (lautet|heisst) die definition|erkläre,? was)\b", re.IGNORECASE)


def abschreibbar(task: dict, theorie: dict | None) -> str | None:
    """Lässt sich die Antwort direkt aus der unmittelbar vorangegangenen Theorie abschreiben?"""
    if not theorie:
        return None
    frage = task.get("frage") or ""
    konzept = staemme(theorie.get("konzept") or "")
    if _DEFINITIONSFRAGE.search(frage) and konzept and all(
            _kommt_vor(k, staemme(frage)) for k in konzept):
        return ("Die Frage ist eine reine Definitionsabfrage direkt nach der Definition. "
                "Lass das Konzept stattdessen auf einen neuen Fall anwenden.")
    erwartet = task.get("erwartete_antwort") or ""
    if len(woerter(erwartet)) >= 6:
        theorie_text = f"{theorie.get('inhalt', '')} {theorie.get('beispiel', '')}"
        for satz in re.split(r"(?<=[.!?])\s+", theorie_text):
            anteil, _ = ueberschneidung(erwartet, satz)
            if anteil >= 0.8:
                return ("Die erwartete Antwort steht fast wörtlich im eben gezeigten Theorietext. "
                        "Stelle eine Aufgabe, die eigenes Denken verlangt.")
    return None


# ---------------------------------------------------------------- D-03

_DEFENSIV = re.compile(
    r"^\W*(im|laut|gemäss|gemäß)?\s*(dem\s+)?(lektions)?material\s+(wird|werden|steht|stehen|ist|"
    r"sind|enthält|erwähnt|findet|gibt|nennt|beschreibt|sagt)\b[^.!?]*\b(nicht|keine?n?)\b"
    r"|^\W*das\s+(lektions)?material\s+(enthält|nennt|beschreibt|erwähnt|gibt)\s+(keine|nicht)",
    re.IGNORECASE)


def defensiver_einstieg(text: str) -> str | None:
    t = (text or "").strip()
    if _DEFENSIV.search(t):
        return ("Die Antwort beginnt defensiv mit einem Verweis darauf, was im Material fehlt. "
                "Beginne mit dem, was stimmt oder was du erklären kannst.")
    if len(re.findall(r"\bMaterial", t)) > 2:
        return "Die Antwort verweist zu oft auf «das Material». Erkläre direkt."
    return None


def zu_aehnlich(neu: str, bisherige: list[str], schwelle: float = 0.6) -> str | None:
    """Wiederholt ein neuer Text im Wesentlichen einen bereits gezeigten?"""
    if len(staemme(neu)) < 8:
        return None
    for alt in bisherige:
        anteil, _ = ueberschneidung(neu, alt)
        if anteil >= schwelle:
            return (f"Die Erklärung wiederholt einen bereits gezeigten Text zu {round(anteil * 100)} "
                    "Prozent. Bring einen neuen Zugang statt derselben Formulierung.")
    return None


def aehnlichkeit(neu: str, bisherige: list[str]) -> float:
    """Höchster Anteil der Inhaltswörter von `neu`, die schon in einem früheren Text standen."""
    return max((ueberschneidung(neu, alt)[0] for alt in bisherige), default=0.0)


def pruefe_aufgabe(task: dict, theorie: dict | None, direkt_nach_theorie: bool,
                   lesson: dict | None = None) -> str | None:
    """Alle deterministischen Prüfungen einer Aufgabe (D-01, T-01)."""
    fach = fachvokabular(lesson) if lesson else None
    themen = themenwoerter(lesson) if lesson else None
    return (pruefe_felder(task, ("inhalt", "frage"))
            or (thema_verfehlt(f"{task.get('inhalt', '')} {task.get('frage', '')}", lesson)
                if lesson else None)
            or loesungswort_in_aufgabe(task, fach)
            or beispiel_wiederverwendet(task, theorie, themen)
            or (abschreibbar(task, theorie) if direkt_nach_theorie else None))


_SIE_ANREDE = re.compile(
    r"\b(begründen|erklären|beschreiben|nennen|vergleichen|überlegen|geben|berechnen|schreiben|"
    r"bestimmen|stellen|prüfen|ergänzen|entscheiden|beurteilen|zeigen|finden|lesen|denken|"
    r"schätzen|ordnen|wenden|formulieren|begründe[nt]?) Sie\b|\bIhre?[nmrs]? (Antwort|Meinung|"
    r"Lösung|Begründung|Entscheidung|Einschätzung)\b|\bkönnen Sie\b|\bwürden Sie\b", re.UNICODE)


def sie_anrede(text: str) -> str | None:
    """Die Lernenden werden geduzt. Erkennt die Höflichkeitsform in Aufgaben."""
    m = _SIE_ANREDE.search(text or "")
    if m:
        return (f"Die Aufgabe spricht die Lernenden mit «Sie» an («{m.group(0)}»). "
                "Duze sie durchgehend.")
    return None


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
    return leere_ankuendigung(text) or sie_anrede(text)
