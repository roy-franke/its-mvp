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
    # ------------------------------------------------------------ Auftrag 2 (Oktober 2026)
    # Diese Regeln stehen bewusst nicht im Systemprompt (der bliebe sonst nicht
    # unverändert, D-10); die Anweisungen dazu gehen im Benutzerteil mit, die
    # Prüfung läuft deterministisch nach der Generierung.
    "D08_KEINE_DOPPELTE_THEORIE": {
        "paket": "D-08", "bereich": "erklaerung", "im_prompt": False,
        "titel": "Keine doppelte Theorie",
        "regel": "Ein Konzept, zu dem in der Sequenz schon Theorie gezeigt wurde, löst keine automatische "
                 "Theorie mehr aus; eine neue Theorie wiederholt nicht die vorangehende.",
        "pruefbar": True,
    },
    "D09_AUFGABE_ZUR_THEORIE": {
        "paket": "D-09", "bereich": "aufgabe", "im_prompt": False,
        "titel": "Aufgabe passt zur vorangehenden Theorie",
        "regel": "Eine Aufgabe direkt nach einer Theorie behandelt genau deren Konzept, nicht das Oberthema "
                 "oder ein anderes Thema, und verlangt nur Fachbegriffe aus gezeigten Theorien.",
        "pruefbar": True,
    },
    "D10_ELEMENTE_IN_DER_FRAGE": {
        "paket": "D-10", "bereich": "aufgabe", "im_prompt": False,
        "titel": "Frage nennt alle erwarteten Elemente",
        "regel": "Die Aufgabe legt 1 bis 4 erwartete Elemente fest, die Frage nennt jedes davon; eine Frage, "
                 "die sprachlich eine Sache verlangt, hat genau ein Element. Bewertet wird nur danach.",
        "pruefbar": True,
    },
    "D11_KEINE_KOPIE": {
        "paket": "D-11", "bereich": "bewertung", "im_prompt": False,
        "titel": "Kopierte Antworten werden nicht bewertet",
        "regel": "Besteht eine Antwort zu mindestens 60 Prozent aus Wort-Vierergruppen angezeigter Texte "
                 "oder des Materials, wird sie nicht bewertet; bei teilweiser Übernahme zählt nur die "
                 "Eigenleistung.",
        "pruefbar": True,
    },
    "D12_URTEIL_UND_TEXT": {
        "paket": "D-12", "bereich": "bewertung", "im_prompt": False,
        "titel": "Urteil und Bewertungstext passen zusammen",
        "regel": "Lautet das Urteil «falsch», sagt der Text nicht «(grundsätzlich) richtig»; lautet es "
                 "«korrekt», sagt er nicht «stimmt nicht».",
        "pruefbar": True,
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
        regeln = [r for r in REGELN.values() if r["bereich"] == key and r.get("im_prompt", True)]
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
benötigen benötigt benötigst benötigte brauchen braucht brauchst erhalten erhält erhältst
menge mengen mengenangabe mengenangaben richtig richtige richtigen richtiger möchte möchtest
möchten insgesamt übrig
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

ELEMENT_STATUS = ("korrekt", "ungenau", "falsch", "fehlt")


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
    # «ungenau»: sachlich zutreffend, aber zu allgemein oder unpräzis (etwa
    # «Kausalhaftung» statt «Tierhalterhaftung»). Das ist ein Teilerfolg, kein Fehler.
    if "korrekt" in status or "ungenau" in status:
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


_VERGLEICH = re.compile(r"(vergleiche?\b|im vergleich (zu|mit)\b|anders als bei\b|gegenüber)[^.?!]*",
                        re.IGNORECASE)


def ohne_vergleich(frage: str) -> str:
    """Entfernt den Vergleichsteil einer Frage.

    «… und vergleiche dies mit der Tierhalterhaftung» nennt ein
    Vergleichsobjekt, nicht die Lösung. Im vollen Evaluationslauf waren vier
    der zehn Lösungswort-Treffer solche Vergleiche.
    """
    return _VERGLEICH.sub(" ", frage)


def loesungswort_in_titel(task: dict, fachwoerter: set[str] | None = None) -> str | None:
    """D-13: Verrät der Titel die gesuchte Lösung?

    «Kausalhaftung beim Spielplatz» über der Frage, welche Art der Haftung
    greift, nimmt die Antwort vorweg. Geprüft werden die Lösungsbegriffe wie
    bei der Frage, dazu das Konzept der Aufgabe, wenn die erwartete Antwort es
    verlangt. Angaben aus dem Fall und Themenwörter der Lektion sind erlaubt.
    """
    titel = (task.get("titel") or "").strip()
    if not titel or (task.get("aufgabentyp") or "").lower() in ("multiple_choice", "multiple-choice", "mc"):
        return None
    titel_staemme = staemme(titel)
    fall_staemme = staemme(task.get("inhalt") or "")
    begriffe = list(schluesselbegriffe(task))
    erwartet = " ".join([str(task.get("erwartete_antwort") or "")]
                        + [e["erwartet"] for e in elemente_normalisieren(task.get("erwartete_elemente"))])
    konzept = (task.get("konzept") or "").strip()
    if konzept and staemme(konzept) and all(_kommt_vor(t, staemme(erwartet)) for t in staemme(konzept)):
        begriffe.append(konzept)
    for begriff in begriffe:
        if re.search(r"\d", begriff):
            continue
        teile = staemme(begriff)
        if not teile or all(_kommt_vor(t, fall_staemme) for t in teile):
            continue
        if fachwoerter is not None and all(any(t.startswith(w) for w in themenwurzeln(fachwoerter)) for t in teile):
            continue
        if fachwoerter is not None and not all(_kommt_vor(t, fachwoerter) for t in teile):
            continue
        if all(_kommt_vor(t, titel_staemme) for t in teile):
            return (f"Der Titel «{titel}» verrät die Lösung («{begriff}»). Wähle einen neutralen Titel, der "
                    "nur die Situation beschreibt (zum Beispiel «Unfall auf dem Spielplatz»), nicht das Ergebnis.")
    return None


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
    frage_staemme = staemme(ohne_vergleich(task.get("frage") or ""))
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


def fallwoerter(theorie: dict | None, themen: set[str] | None = None, n: int = 10) -> list[str]:
    """Die prägenden Wörter des Theorie-Beispiels, wie sie im Text stehen.

    Das sind die Wörter, die dieselbe Prüfung wie beispiel_wiederverwendet als
    Fallwörter zählt (nicht in der Erklärung, keine Themen- oder Stoppwörter).
    Sie gehen vorab als ausdrückliche Verbotsliste an das Modell: Eine konkrete
    Liste («Hund, Passant, beissen») befolgt es zuverlässiger als die
    allgemeine Anweisung, einen anderen Fall zu wählen.

    D-13: Die Merkmale des Konzepts (Feld merkmale der Theorie) landen nie auf
    der Liste. Gesucht ist ein neuer Fall, nicht ein Fall ohne das prägende
    Merkmal.
    """
    if not theorie or not (theorie.get("beispiel") or "").strip():
        return []
    ausnahmen = staemme(" ".join([theorie.get("konzept") or "", theorie.get("inhalt") or ""]
                                 + merkmale_bereinigen(theorie.get("merkmale")))) | (themen or set())
    out, gesehen = [], set()
    for w in woerter(theorie["beispiel"]):
        st = stamm(w)
        if _kommt_vor(st, ausnahmen) or any(gleicher_stamm(st, g) for g in gesehen):
            continue
        gesehen.add(st)
        out.append(w)
    return out[:n]


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
            or loesungswort_in_titel(task, fach)
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


# ---------------------------------------------------------------- D-08
#
# Konzeptnamen schreibt das Modell nicht immer gleich («Kausalhaftung»,
# «Kausalhaftung ohne Verschulden», «Kausal-Haftung»). Verglichen wird deshalb
# nach Vereinheitlichung und über den Kernbegriff: das längste Inhaltswort.
# Damit gilt «Kausalhaftung» als erklärt, wenn eine Theorie zu «Kausalhaftung
# ohne Verschulden» gezeigt wurde, aber «Tierhalterhaftung» nicht als
# «Haftung».

# Kalibriert mit den beiden Fällen aus dem Feedback vom 29.9.2026
# (tests/daten/doppelte_theorie.json): Kausalhaftung 0.61, Unschärferelation
# 0.51, verschiedene Konzepte 0.0.
THEORIE_AEHNLICH = 0.45


def konzept_normalisieren(name: str | None) -> str:
    n = (name or "").lower().replace("ß", "ss")
    n = re.sub(r"[^a-zäöü0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def kernbegriff(name: str | None) -> str:
    """Stamm des längsten Inhaltsworts eines Konzeptnamens."""
    kandidaten = [w for w in woerter(konzept_normalisieren(name).replace("-", " ")) if len(w) >= 5]
    return stamm(max(kandidaten, key=len)) if kandidaten else ""


def gleiches_konzept(a: str | None, b: str | None) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    na, nb = konzept_normalisieren(a), konzept_normalisieren(b)
    if na == nb or na.replace(" ", "") == nb.replace(" ", ""):
        return True
    ka, kb = kernbegriff(a), kernbegriff(b)
    if not ka or not kb:
        return False
    return ka == kb or (gleicher_stamm(ka, kb) and abs(len(ka) - len(kb)) <= 3)


# ---------------------------------------------------------------- D-09

def _stamm_passt(t: str, a: str) -> bool:
    """Deckt der Stamm a aus dem Aufgabenkonzept den Stamm t aus dem Theoriekonzept ab?

    Gleich, gebeugt (kleiner Unterschied am Ende) oder spezifischer (Zusammensetzung,
    die t enthält). Allgemeiner ist nicht erlaubt: «haftung» deckt «tierhalterhaftung»
    nicht ab.
    """
    if t == a or (a.startswith(t) and len(a) - len(t) <= 3) or (t.startswith(a) and len(t) - len(a) <= 3):
        return True
    return len(t) >= 5 and t in a


def konzept_ergaenzen(task: dict, theorie: dict | None) -> None:
    """D-09: Lässt das Modell das Feld konzept weg (Evaluation vom 12.10.2026,
    1 von 20 Aufgaben), obwohl Titel oder Frage das Konzept der unmittelbar
    vorangehenden Theorie nennen, wird dieses übernommen. Sonst bleibt das Feld
    leer, und aufgabe_passt_zur_theorie verlangt eine Korrektur."""
    if not theorie or (task.get("konzept") or "").strip():
        return
    tk = (theorie.get("konzept") or "").strip()
    if not tk:
        return
    t_staemme = [x for x in staemme(konzept_normalisieren(tk)) if len(x) >= 5]
    text = staemme(" ".join(str(task.get(f) or "") for f in ("titel", "frage")))
    if t_staemme and all(any(_stamm_passt(t, w) for w in text) for t in t_staemme):
        task["konzept"] = tk


def aufgabe_passt_zur_theorie(task: dict, theorie: dict | None) -> str | None:
    """D-09: Das Konzept einer Aufgabe direkt nach einer Theorie ist das Konzept
    dieser Theorie. Ein anderes Thema oder das Oberthema ist ein Verstoss."""
    if not theorie:
        return None
    tk = (theorie.get("konzept") or "").strip()
    ak = (task.get("konzept") or "").strip()
    if not tk:
        return None
    nt, na = konzept_normalisieren(tk), konzept_normalisieren(ak)
    if nt == na or nt.replace(" ", "") == na.replace(" ", ""):
        return None
    t_staemme = [x for x in staemme(nt) if len(x) >= 5] or list(staemme(nt))
    a_staemme = list(staemme(na))
    if ak and all(any(_stamm_passt(t, a) for a in a_staemme) for t in t_staemme):
        return None
    return (f"Die Aufgabe behandelt «{ak or 'kein Konzept'}», die unmittelbar vorangehende Theorie aber "
            f"«{tk}». Stelle die Aufgabe genau zum Konzept «{tk}» (nicht zum Oberthema und nicht zu "
            f"einem anderen Thema) und setze im Feld konzept «{tk}».")


def begriff_nicht_erklaert(task: dict, erklaerte_texte: str, lesson: dict | None) -> str | None:
    """D-09: Verlangt die Aufgabe einen zentralen Fachbegriff, der in keiner gezeigten
    Theorie vorkommt? Gemeldet werden nur klare Fälle: ein Fachbegriff der Lektion,
    von dem kein einziger Wortstamm in den bisherigen Erklärungen steht."""
    if not lesson or not erklaerte_texte.strip():
        return None
    bekannt = staemme(erklaerte_texte)
    fach = fachvokabular(lesson)
    # Die Schlüsselbegriffe sind die Fachbegriffe, die die Antwort (und damit die
    # erwarteten Elemente) verlangt; die Elemente selbst sind Beschreibungen.
    for begriff in list(task.get("schluesselbegriffe") or []):
        if not isinstance(begriff, str) or re.search(r"\d", begriff):
            continue
        teile = [x for x in staemme(begriff) if len(x) >= 6]
        if len(teile) != 1 or len(staemme(begriff)) > 2:
            continue                       # nur einzelne Fachbegriffe, keine Beschreibungen
        t = teile[0]
        if _kommt_vor(t, fach) and not _kommt_vor(t, bekannt):
            return (f"Die Aufgabe verlangt den Fachbegriff «{begriff}», der in keiner bisher gezeigten "
                    "Theorie vorkommt. Stelle die Aufgabe so, dass sie sich mit der vorangehenden "
                    "Theorie beantworten lässt.")
    return None


# ---------------------------------------------------------------- D-13
#
# Nach einer Theorie zur Tierhalterhaftung entstand ein Fall ohne Tier (Ball
# zerbricht Fensterscheibe), und die Musterlösung folgte dem Etikett statt dem
# Sachverhalt. Theorie und Aufgabe nennen deshalb die Merkmale, an denen man
# das Konzept in einem Fall erkennt; die Aufgabe gibt zu jedem Merkmal an, wo
# es im Fall steht. Klare Fälle prüft dieser Code, die übrigen die
# Gegenprüfung der Musterlösung (tutor.pruefe_musterloesung).

def merkmale_bereinigen(roh) -> list[str]:
    """Merkmale als kurze Texte (Theorie: Liste von Texten, Aufgabe: auch Objekte)."""
    if not isinstance(roh, list):
        return []
    out = []
    for m in roh:
        text = m.get("merkmal") if isinstance(m, dict) else m
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return out[:3]


def merkmale_der_aufgabe(roh) -> list[dict]:
    """[{merkmal, im_fall}] aus dem Feld merkmale einer Aufgabe; alte Texte ohne Fundstelle."""
    if not isinstance(roh, list):
        return []
    out = []
    for m in roh:
        if isinstance(m, dict) and str(m.get("merkmal") or "").strip():
            out.append({"merkmal": str(m["merkmal"]).strip(), "im_fall": str(m.get("im_fall") or "").strip()})
        elif isinstance(m, str) and m.strip():
            out.append({"merkmal": m.strip(), "im_fall": ""})
    return out[:3]


def _steht_im_fall(text: str, fall_staemme: set[str]) -> bool:
    teile = [t for t in staemme(text) if len(t) >= 3] or [stamm(w) for w in re.findall(r"[A-Za-zÄÖÜäöü]{3,}", text)]
    return bool(teile) and any(_kommt_vor(t, fall_staemme) for t in teile)


def merkmale_fehlen_im_fall(task: dict, theorie: dict | None = None) -> str | None:
    """D-13: Enthält der Fall die Merkmale seines Konzepts?

    Verlangt sind die Merkmale der unmittelbar vorangehenden Theorie, sonst
    die der Aufgabe selbst. Ein Merkmal gilt als vorhanden, wenn es selbst im
    Fall steht oder die Aufgabe eine Fundstelle nennt, die wirklich im Fall
    steht («Tier» → «Hund»). Ob die Fundstelle das Merkmal inhaltlich trägt,
    prüft die Gegenprüfung.
    """
    fall = staemme(task.get("inhalt") or "")
    eintraege = merkmale_der_aufgabe(task.get("merkmale"))
    verlangt = merkmale_bereinigen((theorie or {}).get("merkmale")) or [e["merkmal"] for e in eintraege]
    if not verlangt:
        return None                       # alte Theorien und Aufgaben ohne Merkmale
    konzept = (task.get("konzept") or (theorie or {}).get("konzept") or "dem Konzept").strip()
    fehlend = []
    for merkmal in verlangt:
        if _steht_im_fall(merkmal, fall):
            continue
        m_staemme = staemme(merkmal) or {stamm(merkmal)}
        treffer = [e for e in eintraege
                   if any(gleicher_stamm(a, b) for a in m_staemme for b in (staemme(e["merkmal"]) or {stamm(e["merkmal"])}))]
        if any(e["im_fall"] and _steht_im_fall(e["im_fall"], fall) for e in treffer):
            continue
        fehlend.append(merkmal)
    if fehlend:
        return (f"Der Fall enthält das prägende Merkmal von «{konzept}» nicht: " + ", ".join(f"«{m}»" for m in fehlend)
                + ". Erfinde einen neuen Fall, in dem dieses Merkmal vorkommt (in neuer Form, nicht wie im Beispiel "
                  "der Theorie), und gib im Feld merkmale an, wo es im Fall steht.")
    return None


def loesungen_stimmen_ueberein(a: str, b: str, lesson: dict | None = None) -> bool:
    """D-13: Klarer Fall einer Übereinstimmung zweier Lösungen.

    Verglichen werden die Fachbegriffe (Stämme ab fünf Zeichen, die im
    Vokabular der Lektion vorkommen). Nennen beide Lösungen dieselben
    Fachbegriffe und keine verneint, was die andere bejaht, gilt das als
    Übereinstimmung. Alles andere entscheidet das Modell; dieser Vergleich
    meldet nie eine Abweichung.
    """
    if not a.strip() or not b.strip():
        return False
    fach = fachvokabular(lesson) if lesson else None

    def kern(text: str) -> set[str]:
        return {t for t in staemme(text) if len(t) >= 5 and (fach is None or _kommt_vor(t, fach))}
    ka, kb = kern(a), kern(b)
    if not ka or not kb:
        return False
    verneint = re.compile(r"\b(nicht|kein\w*)\b", re.IGNORECASE)
    if bool(verneint.search(a)) != bool(verneint.search(b)):
        return False
    return all(_kommt_vor(t, kb) for t in ka) and all(_kommt_vor(t, ka) for t in kb)


def liste_texte(roh, n: int = 3) -> list[str]:
    if not isinstance(roh, list):
        return []
    return [str(x).strip() for x in roh if isinstance(x, (str, int, float)) and str(x).strip()][:n]


# ---------------------------------------------------------------- D-10

def elemente_normalisieren(roh) -> list[dict]:
    """D-14: Erwartete Elemente als [{dimension, erwartet}].

    Neue Aufgaben speichern zu jeder Dimension den erwarteten Inhalt. Ältere
    Aufgaben haben nur Texte; sie gelten als Dimension ohne Inhalt und werden
    wie bisher bewertet.
    """
    if not isinstance(roh, list):
        return []
    out = []
    for e in roh:
        if isinstance(e, dict):
            dim = str(e.get("dimension") or e.get("element") or "").strip()
            erwartet = str(e.get("erwartet") or e.get("inhalt") or "").strip()
            if dim or erwartet:
                out.append({"dimension": dim or erwartet, "erwartet": erwartet})
        elif isinstance(e, str) and e.strip():
            out.append({"dimension": e.strip(), "erwartet": ""})
    return out[:4]


def elemente_bereinigen(roh) -> list[str]:
    """Die Dimensionen der erwarteten Elemente (beide Formate, D-10 und D-14)."""
    return [e["dimension"] for e in elemente_normalisieren(roh)]


_MEHRTEILIG = re.compile(r"\b(und|sowie|sind|alle|beiden?|jeweils|mehrere|warum|weshalb|wieso|begründe|"
                         r"erkläre|beschreibe|nenne\s+\w+\s+und)\b|,", re.IGNORECASE)
_EINE_SACHE = re.compile(
    r"^\W*(welche[rsmn]?\b[^?]*?\b(ist|war|wäre|liegt|greift|gilt|trifft|fehlt|besteht|eignet sich)\b"
    r"|wer\b[^?]*?\b(ist|war|haftet|muss|trägt|zahlt|hat|wird)\b"
    r"|was\s+ist\s+(der|die|das)\b)", re.IGNORECASE)


def frage_verlangt_eine_sache(frage: str) -> bool:
    """Klare Fälle einer Frage, die sprachlich genau eine Sache verlangt (D-10).

    «Welche der vier Voraussetzungen ist hier am stärksten erkennbar?» oder
    «Wer ist für den beschädigten Wagen verantwortlich?». Sobald die Frage
    weitere Teile nennt («und», «warum», «begründe», mehrere Sätze), gilt sie
    nicht mehr als einteilig.
    """
    f = (frage or "").strip()
    if not f or f.count("?") > 1 or len(re.findall(r"[.!?]\s+\S", f)) > 0:
        return False
    if _MEHRTEILIG.search(f):
        return False
    return bool(_EINE_SACHE.match(f))


def elemente_passen_zur_frage(task: dict) -> str | None:
    """D-10: Erwartete Elemente sind festgelegt, und eine einteilige Frage hat genau eines."""
    elemente = elemente_bereinigen(task.get("erwartete_elemente"))
    if not elemente:
        return ("Lege im Feld erwartete_elemente 1 bis 4 Teile fest, die die Antwort enthalten soll, "
                "und nenne jeden davon in der Frage.")
    if len(elemente) > 1 and frage_verlangt_eine_sache(task.get("frage", "")):
        return (f"Die Frage verlangt sprachlich genau eine Sache, es sind aber {len(elemente)} erwartete "
                "Elemente festgelegt (" + "; ".join(elemente) + "). Formuliere die Frage so, dass sie jeden "
                "Teil ausdrücklich nennt (zum Beispiel «Nenne … und …»), oder lege genau ein Element fest.")
    return None


def elemente_anzahl_passt(bewertung: dict, festgelegt: list[str]) -> str | None:
    """D-10: Die Bewertung prüft genau die bei der Aufgabe festgelegten Elemente."""
    if not festgelegt:
        return None
    n = len([e for e in bewertung.get("elemente") or [] if isinstance(e, dict)])
    if n != len(festgelegt):
        return (f"Prüfe genau die {len(festgelegt)} festgelegten Elemente (du hast {n} zurückgegeben): "
                + "; ".join(festgelegt) + ".")
    return None


# ---------------------------------------------------------------- D-11
#
# Wer die Theorie kopiert und als Antwort abschickt, erbringt keine
# Eigenleistung. Gemessen wird der Anteil der Wort-Vierergruppen der Antwort,
# die wörtlich in einem angezeigten Text oder im Lektionsmaterial stehen.
# Einzelne Fachbegriffe ergeben keine Vierergruppe und lösen nichts aus.

KOPIE_SCHWELLE = 0.6           # ab hier: Kopie, keine Bewertung (Entscheid E3)
TEILKOPIE_SCHWELLE = 0.25      # ab hier: übernommene Teile gehen als Hinweis an die Bewertung
KOPIE_MIN_WOERTER = 12         # kürzere Antworten werden nie als Kopie gewertet
_N = 4


def _wortfolge(text: str) -> list[str]:
    return re.findall(r"[a-zäöü0-9]+", (text or "").lower().replace("ß", "ss"))


def _gruppen(woerter: list[str]) -> set[tuple]:
    return {tuple(woerter[i:i + _N]) for i in range(len(woerter) - _N + 1)}


def kopie_pruefen(antwort: str, quellen: list[tuple[str, str]]) -> dict:
    """Anteil wörtlich übernommener Wortfolgen und die Quelle mit den meisten Treffern."""
    w = _wortfolge(antwort)
    if len(w) < KOPIE_MIN_WOERTER:
        return {"anteil": 0.0, "quelle": None, "passagen": [], "woerter": len(w)}
    positionen = list(range(len(w) - _N + 1))
    getroffen: set[int] = set()
    beste, beste_n = None, 0
    for name, text in quellen:
        g = _gruppen(_wortfolge(text))
        treffer = {i for i in positionen if tuple(w[i:i + _N]) in g}
        if len(treffer) > beste_n:
            beste, beste_n = name, len(treffer)
        getroffen |= treffer
    anteil = len(getroffen) / len(positionen) if positionen else 0.0
    # zusammenhängende übernommene Passagen (für die Bewertung bei Teilkopien)
    passagen, start, ende = [], None, None
    for i in sorted(getroffen):
        if start is None or i > ende + 1:
            if start is not None:
                passagen.append(" ".join(w[start:ende + _N]))
            start = i
        ende = i
    if start is not None:
        passagen.append(" ".join(w[start:ende + _N]))
    return {"anteil": round(anteil, 2), "quelle": beste, "passagen": passagen, "woerter": len(w)}


# ---------------------------------------------------------------- D-12
#
# Das Urteil leitet der Code aus den Elementen ab (D-05). Weicht es vom Urteil
# des Modells ab, wurde das Feedback für ein anderes Urteil geschrieben: Der
# Screenshot zeigte «Noch nicht ganz» (falsch) mit dem Text «grundsätzlich
# richtig». Klare Widersprüche zwischen Urteil und Text sind deshalb ein
# Regelverstoss, die Bewertung wird mit Korrekturhinweis wiederholt.

_POSITIV = re.compile(
    r"\b(grundsätzlich|im kern|im grunde|weitgehend|im wesentlichen|völlig|absolut|vollkommen|ganz)\s+"
    r"(richtig|korrekt|zutreffend)\b"
    r"|^\W*(richtig|korrekt|genau|super|sehr gut|gut gemacht|perfekt)\b(?!\s+ist)"
    r"|\bdeine antwort (ist|war) (richtig|korrekt|zutreffend)\b", re.IGNORECASE)
_NEGATIV = re.compile(
    r"\b(ist|wäre|war) (leider )?(falsch|nicht richtig|nicht korrekt)\b|\bstimmt (leider )?nicht\b"
    r"|^\W*(falsch|leider nicht|noch nicht ganz|nicht ganz)\b", re.IGNORECASE)


def urteil_widerspricht_text(bewertung: dict) -> str | None:
    urteil = urteil_aus_elementen(bewertung.get("elemente"), bool(bewertung.get("sachlicher_widerspruch"))) \
        or bewertung.get("bewertung")
    text = str(bewertung.get("feedback") or "")
    if urteil == "falsch":
        m = _POSITIV.search(text)
        if m and not re.search(r"\b(nicht|kein|un)\w*\s+(\w+\s+)?" + re.escape(m.group(0).strip()), text,
                               re.IGNORECASE):
            return (f"Das Urteil «falsch» passt nicht zum Feedback («{m.group(0).strip()}»). Ist die Antwort "
                    "im Kern richtig, bewerte die Elemente entsprechend (korrekt oder ungenau); sonst "
                    "formuliere das Feedback passend zum Urteil «falsch».")
    if urteil == "korrekt":
        m = _NEGATIV.search(text)
        if m:
            return (f"Das Urteil «korrekt» passt nicht zum Feedback («{m.group(0).strip()}»). Bewerte die "
                    "Elemente so, wie das Feedback die Antwort beurteilt, oder passe das Feedback an.")
    return None


def theorietext(t: dict | None) -> str:
    t = t or {}
    return " ".join(str(t.get(k) or "") for k in ("inhalt", "beispiel")).strip()


# ---------------------------------------------------------------- T-13

_VERKLEBT_SATZ = re.compile(r"([a-zäöüß]{2})([.:!?])([A-ZÄÖÜ][a-zäöü])")
_VERKLEBT_WORT = re.compile(r"\b([A-ZÄÖÜ]?[a-zäöüß]{3,})([A-ZÄÖÜ][a-zäöüß]{2,})\b")


def saetze_trennen(text: str) -> str:
    """Fügt nach Satzzeichen einen Leerschlag ein, wo er offensichtlich fehlt.

    «messbar.Quantenverschränkung» wird zu «messbar. Quantenverschränkung».
    Abkürzungen wie «z.B.» bleiben unverändert (Kleinbuchstabe danach).
    """
    return _VERKLEBT_SATZ.sub(r"\1\2 \3", text or "")


def verklebte_stellen(text: str, n: int = 3) -> list[str]:
    """Beispiele für Stellen, an denen Zeilenumbrüche verloren gingen (für die Materialprüfung)."""
    stellen = [(m.start(), m.group(0)) for m in _VERKLEBT_STELLE.finditer(text or "")]
    stellen += [(m.start(), m.group(0)) for m in _VERKLEBT_WORT.finditer(text or "")]
    treffer = [t for _, t in sorted(stellen)]
    return list(dict.fromkeys(treffer))[:n] if len(treffer) >= 2 else []


_VERKLEBT_STELLE = re.compile(r"[A-Za-zÄÖÜäöüß]*[a-zäöüß]{2}[.:!?][A-ZÄÖÜ][a-zäöüß]+")


# ---------------------------------------------------------------- T-10
#
# Gültiges JSON heisst noch nicht, dass die Felder stimmen. Bei der
# Einstufung lieferte das Modell eine Liste von Objekten statt Texten, und
# das Frontend zeigte «[object Object]». Jeder Aufruf von chat_json prüft
# deshalb die erwarteten Felder und Typen. Eine falsche Struktur löst den
# Korrekturversuch aus; ist auch der letzte Versuch falsch, greift der
# Fallback (siehe llm.chat_json).

STRUKTUR_PRAEFIX = "Falsche Struktur:"

# Schema: Feld -> (Typ, Pflicht). Typen: "text", "liste_text", "liste_objekt", "bool", "liste".
STRUKTUR: dict[str, dict[str, tuple[str, bool]]] = {
    "EINSTUFUNG_BEWERTEN": {"level": ("text", True), "begruendung": ("text", False)},
    "THEORIE_SCHRITT": {"titel": ("text", False), "inhalt": ("text", True), "beispiel": ("text", False),
                        "konzept": ("text", False), "quelle": ("text", False), "merkmale": ("liste", False)},
    "NAECHSTE_AUFGABE": {"titel": ("text", False), "inhalt": ("text", False), "frage": ("text", True),
                         "konzept": ("text", False), "erwartete_antwort": ("text", False),
                         "schluesselbegriffe": ("liste_text", False), "optionen": ("liste", False),
                         "erwartete_elemente": ("liste", False), "merkmale": ("liste", False),
                         "alternative_loesungen": ("liste", False)},
    "ANTWORT_BEWERTEN": {"elemente": ("liste_objekt", False), "bewertung": ("text", False),
                         "feedback": ("text", True), "hinweis": ("text", False)},
    "FRAGE_BEANTWORTEN": {"antwort": ("text", True), "konzept": ("text", False)},
    "ABSCHLUSS": {"zusammenfassung": ("text", True), "erreichte_lernziele": ("liste_text", False),
                  "empfehlung": ("text", False)},
    "LERNZIELE_VORSCHLAGEN": {"lernziele": ("liste_text", True)},
    "MATERIAL_PRUEFEN": {"ziele": ("liste_objekt", True), "gesamt": ("text", False)},
    "WITZ": {"witz": ("text", True)},
    # D-13: Gegenprüfung der Musterlösung
    "MUSTERLOESUNG_PRUEFEN": {"loesung": ("text", True), "offene_punkte": ("liste", False),
                              "merkmale_im_fall": ("bool", False)},
    "MUSTERLOESUNG_VERGLEICHEN": {"uebereinstimmend": ("bool", True), "unterschied": ("text", False)},
}

_TYPNAME = {"text": "ein Text", "liste_text": "eine Liste von Texten",
            "liste_objekt": "eine Liste von Objekten", "liste": "eine Liste", "bool": "true oder false"}


def _typ_ok(wert, typ: str) -> bool:
    if typ == "text":
        return isinstance(wert, str)
    if typ == "bool":
        return isinstance(wert, bool)
    if not isinstance(wert, list):
        return False
    if typ == "liste_text":
        return all(isinstance(x, str) for x in wert)
    if typ == "liste_objekt":
        return all(isinstance(x, dict) for x in wert)
    return True


def struktur_pruefen(data: dict, schritt: str) -> str | None:
    """Prüft Felder und Typen einer Modellantwort (T-10). Gibt den Fehler zurück oder None."""
    schema = STRUKTUR.get(schritt)
    if not schema:
        return None
    probleme = []
    for feld, (typ, pflicht) in schema.items():
        wert = data.get(feld)
        if wert is None or wert == "" or wert == []:
            if pflicht:
                probleme.append(f"Das Feld «{feld}» fehlt oder ist leer.")
            continue
        if not _typ_ok(wert, typ):
            probleme.append(f"Das Feld «{feld}» muss {_TYPNAME[typ]} sein.")
    if probleme:
        return f"{STRUKTUR_PRAEFIX} " + " ".join(probleme) + " Halte dich genau an das verlangte Format."
    return None


def ist_strukturfehler(verstoss: str | None) -> bool:
    return bool(verstoss) and verstoss.startswith(STRUKTUR_PRAEFIX)


FRAGE_FELDER = ("frage", "question", "text", "Frage", "Question", "inhalt", "titel")


def frage_als_text(eintrag) -> str:
    """Einstufungsfrage als Text, auch wenn das Modell Objekte liefert (T-10)."""
    if isinstance(eintrag, str):
        return eintrag.strip()
    if isinstance(eintrag, dict):
        for f in FRAGE_FELDER:
            if isinstance(eintrag.get(f), str) and eintrag[f].strip():
                return eintrag[f].strip()
    return ""


def fragen_normalisieren(roh) -> list[str]:
    if not isinstance(roh, list):
        return []
    return [t for t in (frage_als_text(x) for x in roh) if len(t) >= 8]


# ---------------------------------------------------------------- N-01

_QUELLE_KOPF = re.compile(r"^###\s*Quelle:\s*(.+?)\s*$", re.MULTILINE)


def quellen_der_lektion(lesson: dict) -> list[str]:
    """Namen der Quellen einer Lektion.

    Der Editor setzt das Material aus «### Quelle: <Dateiname>»-Blöcken
    zusammen; die Quellenliste der Lektion (Feld `quellen`) nennt dieselben
    Namen. Lektionen ohne Gliederung haben keine Quellen.
    """
    namen = [m.strip() for m in _QUELLE_KOPF.findall(lesson.get("material") or "")]
    namen += [str(q.get("name", "")).strip() for q in lesson.get("quellen") or [] if isinstance(q, dict)]
    out: list[str] = []
    for n in namen:
        if n and n not in out:
            out.append(n)
    return out


def _quellen_schluessel(name: str) -> str:
    n = name.strip().strip("«»\"'`").lower()
    n = re.sub(r"^(quelle|source)\s*:\s*", "", n)
    n = re.sub(r"\.[a-z0-9]{2,5}$", "", n)          # Dateiendung
    return re.sub(r"[\s_\-]+", " ", n).strip()


def quelle_pruefen(angabe, lesson: dict) -> str | None:
    """Gibt den exakten Quellennamen der Lektion zurück, wenn die Angabe des
    Modells einer existierenden Quelle entspricht, sonst None (N-01).

    Toleriert werden Gross-/Kleinschreibung, fehlende Dateiendung und ein
    vorangestelltes «Quelle:». Eine erfundene Quelle wird nie angezeigt.
    """
    if not isinstance(angabe, str) or not angabe.strip():
        return None
    ziel = _quellen_schluessel(angabe)
    for name in quellen_der_lektion(lesson):
        if _quellen_schluessel(name) == ziel:
            return name
    return None


def quelle_fuer_abschnitt(lesson: dict, abschnitt: str) -> str | None:
    """Aus welcher Quelle stammt ein Materialabschnitt (für Fallback-Schritte)?"""
    material = lesson.get("material") or ""
    teile = _QUELLE_KOPF.split(material)
    # split liefert [vor, name1, text1, name2, text2, ...]
    probe = re.sub(r"\s+", " ", abschnitt or "").strip()[:80]
    if not probe:
        return None
    for i in range(1, len(teile) - 1, 2):
        if probe in re.sub(r"\s+", " ", teile[i + 1]):
            return teile[i].strip()
    return None
