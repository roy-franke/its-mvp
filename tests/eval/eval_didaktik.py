"""Evaluation der didaktischen Pakete gegen ein echtes Sprachmodell.

Läuft NICHT in der normalen Testsuite, sondern von Hand, nachdem ein echtes
Modell in der .env konfiguriert ist (z.B. LLM_PROVIDER=ollama mit qwen3:30b).
Das Skript ruft die Tutorlogik direkt auf (ohne Server), prüft die
Akzeptanzkriterien der Pakete D-01 bis D-12 (Auftrag 2: D-07 bis D-12, T-09; Auftrag 3: D-13 bis D-18
mit den Regressionsfällen aus Anhang B) und schreibt einen lesbaren Bericht nach tests/eval/berichte/.

    python tests/eval/eval_didaktik.py                  # alle Pakete
    python tests/eval/eval_didaktik.py D-01 D-05        # nur ausgewählte
    python tests/eval/eval_didaktik.py --anzahl 3       # schneller Probelauf
    python tests/eval/eval_didaktik.py --mock           # Rauchtest ohne Modell
    python tests/eval/eval_didaktik.py D-07 D-08 D-09 D-10 D-11 D-12 T-09 --haftung <id-der-version-3>
    python tests/eval/eval_didaktik.py D-13 D-14 D-15 D-16 D-17 D-18 T-09        # Auftrag 3
    python tests/eval/eval_didaktik.py D-19 D-20 --haftung <id-der-version-3>    # Auftrag 5

Mit qwen3:30b auf a9-mega dauert ein vollständiger Lauf je nach Anzahl
etwa 30 bis 60 Minuten. Die Anzahl Aufgaben pro Niveau lässt sich mit
--anzahl verkleinern; für die Akzeptanzkriterien sind 10 verlangt.
"""

import argparse
import datetime
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

PAKETE: dict = {}


def paket(name):
    def deco(fn):
        PAKETE[name] = fn
        return fn
    return deco


def lektion(lesson_id: str) -> dict:
    d = Path(os.getenv("ITS_LESSONS_DIR") or ROOT / "app" / "lessons")
    return json.loads((d / f"{lesson_id}.json").read_text(encoding="utf-8"))


# Mit --haftung lässt sich die umfangreiche Lektion «Haftungsrecht Version 3» wählen (Auftrag 2)
HAFTUNG = os.getenv("ITS_EVAL_HAFTUNG", "haftungsrecht")
BRUCH = "bruchbegriff-verstehen-und-anwenden"
QUANTEN = "einfuhrung-in-die-quantenphysik"


class Bericht:
    def __init__(self, provider: str, modell: str):
        self.teile: list[str] = []
        self.ergebnisse: list[tuple[str, str, bool, str]] = []
        self.kopf = (f"# Evaluationsbericht Didaktik\n\n"
                     f"Datum: {datetime.datetime.now():%d.%m.%Y %H:%M}  \n"
                     f"Provider: {provider}  \nModell: {modell}\n")

    def ak(self, paket: str, kriterium: str, ok: bool, detail: str = ""):
        self.ergebnisse.append((paket, kriterium, ok, detail))
        print(f"  {'OK    ' if ok else 'FEHLER'} {paket} {kriterium}" + (f" – {detail}" if detail else ""))

    def abschnitt(self, titel: str, text: str = ""):
        self.teile.append(f"\n## {titel}\n\n{text}".rstrip() + "\n\n")

    def text(self, text: str):
        self.teile.append(text.rstrip() + "\n")

    def schreiben(self) -> Path:
        ziel = ROOT / "tests" / "eval" / "berichte"
        ziel.mkdir(parents=True, exist_ok=True)
        pfad = ziel / f"eval_{datetime.datetime.now():%Y-%m-%d_%H%M}.md"
        zeilen = ["\n## Akzeptanzkriterien\n", "| Paket | Kriterium | Ergebnis | Detail |",
                  "|---|---|---|---|"]
        for p, k, ok, d in self.ergebnisse:
            zeilen.append(f"| {p} | {k} | {'erfüllt' if ok else '**nicht erfüllt**'} | {d} |")
        pfad.write_text(self.kopf + "\n".join(zeilen) + "\n" + "".join(self.teile), encoding="utf-8")
        return pfad


def zitat(text: str, n: int = 600) -> str:
    t = " ".join(str(text or "").split())
    return "> " + (t[:n] + (" …" if len(t) > n else ""))


# ---------------------------------------------------------------- D-01

@paket("D-01")
def eval_d01(b: Bericht, anzahl: int):
    """Fragequalität: kein Lösungswort, kein wiederverwendetes Beispiel."""
    from app import didaktik, tutor
    b.abschnitt("D-01 Fragequalität",
                f"Pro Lektion und Niveau {anzahl} Aufgaben, jeweils direkt nach einem "
                "Theorieschritt erzeugt. Geprüft wird die endgültige Aufgabe (nach einer "
                "allfälligen Neugenerierung).")
    alle = []
    from app import llm
    token_info = []
    for lid in (HAFTUNG, BRUCH):
        lesson = lektion(lid)
        start = len(llm.timings())
        for level in tutor.LEVELS:
            konzepte: list[str] = []
            for i in range(anzahl):
                p = tutor.new_profile()
                p["level"] = level
                p["covered"] = list(konzepte)
                theorie = tutor.generate_theory(lesson, p, [])
                if theorie.get("konzept"):
                    konzepte.append(theorie["konzept"])
                history = [{"type": "task", "payload": theorie}]
                p["covered"] = list(konzepte)
                p["erklaert"] = list(konzepte)
                p["last_type"] = "theorie"
                task = tutor.generate_task(lesson, p, history)
                eintrag = {
                    "lektion": lesson["titel"], "niveau": level, "theorie": theorie, "task": task,
                    "loesungswort": didaktik.loesungswort_in_aufgabe(task, didaktik.fachvokabular(lesson)),
                    "beispiel": didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(lesson)),
                    "sie": didaktik.sie_anrede(f"{task.get('inhalt', '')} {task.get('frage', '')}"),
                    "abschreibbar": didaktik.abschreibbar(task, theorie),
                    "neu_generiert": task.get("_versuche", 1) > 1,
                    "fallback": bool(task.get("_fallback")),
                    "thema": didaktik.thema_verfehlt(
                        " ".join([theorie.get("inhalt", ""), theorie.get("beispiel", ""),
                                  task.get("inhalt", ""), task.get("frage", "")]), lesson),
                }
                alle.append(eintrag)
                print(f"    {lid[:12]} {level:12} {i + 1}/{anzahl}: "
                      f"{'Verstoss' if eintrag['loesungswort'] or eintrag['beispiel'] else 'ok'}")
        neue = llm.timings()[start:]
        prompt_max = max((t.get("prompt_tokens") or 0 for t in neue), default=0)
        token_info.append((lesson["titel"], prompt_max))
    echt = [e for e in alle if not e["fallback"]]
    lw = [e for e in echt if e["loesungswort"]]
    bsp = [e for e in echt if e["beispiel"]]
    ab = [e for e in echt if e["abschreibbar"]]
    neu = [e for e in echt if e["neu_generiert"]]
    b.ak("D-01", "AK 1 keine Aufgabe mit Lösungswort in der Frage", not lw,
         f"{len(lw)} von {len(echt)}")
    b.ak("D-01", "AK 2 kein wiederverwendetes Theorie-Beispiel", not bsp, f"{len(bsp)} von {len(echt)}")
    sie = [e for e in echt if e["sie"]]
    b.ak("D-01", "Lernende werden geduzt", not sie, f"{len(sie)} von {len(echt)} mit «Sie»")
    thema = [e for e in echt if e["thema"]]
    b.ak("D-01", "Theorie und Aufgabe bleiben beim Thema der Lektion", not thema,
         f"{len(thema)} von {len(echt)} themenfremd")
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    for titel, pt in token_info:
        warnung = " – ACHTUNG: nahe am Kontextfenster, Material wird abgeschnitten" if pt and pt > num_ctx - 1100 else ""
        b.text(f"Grösster Prompt in «{titel}»: {pt or 'unbekannt'} Token (Kontextfenster {num_ctx}){warnung}.")
    b.text(f"\nAufgaben insgesamt: {len(alle)}, davon Fallbacks: {len(alle) - len(echt)}. "
           f"Nach einem Regelverstoss neu generiert: {len(neu)}. Abschreibbar trotz Prüfung: {len(ab)}. "
           "Multiple-Choice-Aufgaben: "
           f"{sum(1 for e in echt if e['task'].get('aufgabentyp') == 'multiple_choice')}.")
    typen: dict[str, int] = {}
    for e in echt:
        typen[e["task"].get("aufgabentyp", "?")] = typen.get(e["task"].get("aufgabentyp", "?"), 0) + 1
    b.text("Aufgabentypen: " + ", ".join(f"{k} {v}" for k, v in sorted(typen.items())) + ".")
    # Warum wurde neu generiert? Grober Grund aus dem ersten Satz des Verstosses.
    gruende: dict[str, int] = {}
    for e in echt:
        for v in e["task"].get("_verstoesse") or []:
            k = str(v).split(":")[0].split(".")[0][:70]
            gruende[k] = gruende.get(k, 0) + 1
    if gruende:
        b.text("\nGründe für Neugenerierungen (alle Versuche): "
               + "; ".join(f"{k} ({n})" for k, n in sorted(gruende.items(), key=lambda x: -x[1])) + ".")
    for titel, liste, feld in (("Verstösse Lösungswort", lw, "loesungswort"),
                               ("Verstösse Beispiel", bsp, "beispiel")):
        if liste:
            b.text(f"\n### {titel}\n")
            for e in liste:
                b.text(f"- {e['lektion']}, {e['niveau']}: «{e['task'].get('frage', '')}» – {e[feld]}")
    if thema:
        b.text("\n### Themenfremde Schritte\n")
        for e in thema:
            b.text(f"- {e['lektion']}, {e['niveau']}: Theorie «{e['theorie'].get('konzept', '')}», "
                   f"Frage «{e['task'].get('frage', '')}» – {e['thema']}\n"
                   f"{zitat(e['theorie'].get('inhalt'), 300)}")
    b.text("\n### Stichprobe zur Sichtprüfung (AK 3)\n")
    for e in random.sample(echt, min(10, len(echt))):
        t = e["task"]
        b.text(f"\n**{e['lektion']} · {e['niveau']} · {t.get('aufgabentyp', '?')}**\n\n"
               f"Theorie ({e['theorie'].get('konzept', '')}):\n\n{zitat(e['theorie'].get('inhalt'))}\n\n"
               f"Beispiel der Theorie:\n\n{zitat(e['theorie'].get('beispiel'))}\n\n"
               f"Aufgabe:\n\n{zitat(t.get('inhalt'))}\n\nFrage:\n\n{zitat(t.get('frage'))}\n\n"
               f"Erwartete Antwort:\n\n{zitat(t.get('erwartete_antwort'))}\n")
    b.ak("D-01", "AK 3 Stichprobe im Bericht", len(echt) > 0, f"{min(10, len(echt))} Aufgaben")


# ---------------------------------------------------------------- Hilfen für ganze Sequenzen

_CLIENT = None


def client():
    """FastAPI-TestClient gegen die echte App mit dem konfigurierten Modell.

    Datenbank in einem Temp-Ordner, Zugangsschutz aus: Die Evaluation soll
    Roys Daten nicht berühren.
    """
    global _CLIENT
    if _CLIENT is None:
        import tempfile
        os.environ["ITS_DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="its_eval_")) / "eval.db")
        os.environ["TEACHER_PASSWORD"] = ""
        os.environ["CLASS_CODE"] = ""
        os.environ["ITS_TRUST_PROXY_HEADERS"] = "false"
        from fastapi.testclient import TestClient
        from app.main import app
        _CLIENT = TestClient(app)
    return _CLIENT


def sequenz(lesson_id: str, name: str, schritte: int = 12, antwort=None) -> tuple[str, list[dict]]:
    """Spielt eine Lernsequenz durch. `antwort(task, events)` liefert die Antwort
    der simulierten lernenden Person; Standard ist die Musterlösung."""
    c = client()
    c.post("/api/learner/login", json={"name": name})
    d = c.post("/api/session/start", json={"lesson_id": lesson_id, "neu_beginnen": True}).json()
    sid = d["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["weiss ich nicht"] * 3})
    adaption = ""
    for _ in range(schritte):
        r = c.post(f"/api/session/{sid}/next" + (f"?adaptation={adaption}" if adaption else "")).json()
        adaption = ""
        if r.get("done"):
            break
        if r["task"]["typ"] != "aufgabe":
            continue
        events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
        voll = [e["payload"] for e in events if e["type"] == "task"][-1]
        text = antwort(voll, events) if antwort else (voll.get("erwartete_antwort") or "weiss nicht")
        a = c.post(f"/api/session/{sid}/answer", json={"answer": text, "confidence": 5}).json()
        if a["adaption"] == "retry":
            a = c.post(f"/api/session/{sid}/answer", json={"answer": text}).json()
        if a.get("adaption") == "wahl_teilweise":          # D-07: einmal ergänzen, dann weiter
            c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"})
            a = c.post(f"/api/session/{sid}/answer", json={"answer": text}).json()
            if a.get("adaption") == "wahl_teilweise":
                c.post(f"/api/session/{sid}/wahl", json={"wahl": "weiter"})
        if a.get("bewertung") in ("unbewertet", "kopie"):
            for w in ("ohne_bewertung", "weiter"):
                c.post(f"/api/session/{sid}/wahl", json={"wahl": w})
        adaption = a["adaption"] if a.get("adaption") in ("simplify", "explain") else ""
    return sid, c.get(f"/api/teacher/sessions/{sid}").json()["events"]


# ---------------------------------------------------------------- D-02

@paket("D-02")
def eval_d02(b: Bericht, anzahl: int):
    """Einführung: keine Aufgabe zu einem vorher nicht erklärten Konzept."""
    from app import tutor
    b.abschnitt("D-02 Einsatzart Einführung",
                "Zwei vollständige Lernsequenzen in der Quantenphysik-Lektion (Einführung) "
                "und eine in der Haftungsrecht-Lektion. Die simulierte lernende Person "
                "antwortet mit der Musterlösung. Geprüft wird jede bewertete Aufgabe gegen "
                "die bis dahin erklärten Konzepte und Texte.")
    verstoesse, aufgaben, eingeschoben = [], 0, 0
    for i, lid in enumerate((QUANTEN, QUANTEN, HAFTUNG)):
        _, events = sequenz(lid, f"Eval D02 {i}")
        erklaert, bisher = [], []
        for e in events:
            bisher.append(e)
            p = e["payload"]
            if e["type"] == "theorie_eingeschoben":
                eingeschoben += 1
            if e["type"] != "task":
                continue
            if p.get("typ") == "theorie" and p.get("konzept"):
                erklaert.append(p["konzept"])
            if p.get("typ") == "aufgabe" and not p.get("fallback"):
                aufgaben += 1
                v = tutor.unerklaert(p, erklaert, tutor.erklaerte_texte(bisher[:-1]))
                if v:
                    verstoesse.append((lid, p, v))
    b.ak("D-02", "AK 1 keine Aufgabe zu unerklärtem Konzept (Einführung)", not verstoesse,
         f"{len(verstoesse)} von {aufgaben} Aufgaben, {eingeschoben} Theorieschritte eingeschoben")
    for lid, p, v in verstoesse:
        b.text(f"- {lid}: «{p.get('frage')}» (erwartet: {p.get('erwartete_antwort')}) – {v}")


# ---------------------------------------------------------------- D-03

@paket("D-03")
def eval_d03(b: Bericht, anzahl: int):
    """Erklärtiefe: neue Zugänge statt Wiederholung, klarer Ton, begründete Anwendungen."""
    import re
    from app import didaktik, tutor
    b.abschnitt("D-03 Erklärtiefe bei Nachfragen",
                "Pro Lektion wird nach dem ersten Theorieschritt zweimal «Theorie dazu» und "
                "danach zweimal «Genauer erklären» angefordert, dazu kommen freie "
                "Verständnisfragen, die das Material nicht abdeckt. Die Ähnlichkeit misst den "
                "Anteil der Inhaltswörter einer Antwort, die schon in einem früher gezeigten "
                "Text zum selben Konzept standen.")
    c = client()
    werte, texte = [], []
    fragen = {QUANTEN: ["Kann man zwischen Welle und Teilchen umschalten?",
                        "Wie ist ein Quantensensor gebaut?"],
              HAFTUNG: ["Haftet man auch, wenn einem das Velo gestohlen wird?",
                        "Gilt das auch in Deutschland?"]}
    for i, lid in enumerate((QUANTEN, HAFTUNG)):
        c.post("/api/learner/login", json={"name": f"Eval D03 {i}"})
        sid = c.post("/api/session/start", json={"lesson_id": lid, "neu_beginnen": True}).json()["session_id"]
        c.post(f"/api/session/{sid}/assess", json={"answers": ["weiss ich nicht"] * 3})
        c.post(f"/api/session/{sid}/next")
        for art in ("theorie", "theorie", "genauer"):
            c.post(f"/api/session/{sid}/chat", json={"message": art, "art": art})
        c.post(f"/api/session/{sid}/next")      # Aufgabe
        c.post(f"/api/session/{sid}/chat", json={"message": "genauer", "art": "genauer"})
        for f in fragen[lid]:
            c.post(f"/api/session/{sid}/chat", json={"message": f})
        events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
        b.text(f"\n### {lektion(lid)['titel']}\n")
        for e in events:
            p = e["payload"]
            if e["type"] == "task" and p.get("typ") == "theorie":
                texte.append(("Theorie", p.get("inhalt", "") + " " + p.get("beispiel", "")))
                b.text(f"**Theorie ({p.get('konzept')})**\n\n{zitat(p.get('inhalt'))}\n\n{zitat(p.get('beispiel'))}\n")
            elif e["type"] == "chat_question":
                b.text(f"**Lernende ({p.get('art')}{', Stufe ' + str(p['stufe']) if p.get('stufe') else ''}):** {p.get('frage')}\n")
            elif e["type"] == "chat_reply":
                texte.append((p.get("art"), p.get("antwort", "")))
                if p.get("aehnlichkeit") is not None:
                    werte.append(p["aehnlichkeit"])
                zusatz = f" (Ähnlichkeit {round(p['aehnlichkeit'] * 100)} %)" if p.get("aehnlichkeit") is not None else ""
                marke = " [ausserhalb Material]" if p.get("ausserhalb_material") else ""
                b.text(f"**Tutor{marke}{zusatz}:**\n\n{zitat(p.get('antwort'))}\n")
    zu_hoch = [w for w in werte if w >= 0.6]
    b.ak("D-03", "AK 1 «Theorie dazu»/«Genauer» wiederholt nicht", not zu_hoch,
         "Ähnlichkeiten: " + ", ".join(f"{round(w * 100)} %" for w in werte))
    defensiv = [t for _, t in texte if didaktik.defensiver_einstieg(t)]
    b.ak("D-03", "AK 3 kein defensiver Einstieg", not defensiv, f"{len(defensiv)} von {len(texte)} Texten")
    for t in defensiv:
        b.text(f"- defensiv: {zitat(t, 200)}")
    # AK 4: Superposition mit begründetem Anwendungsfall
    lesson = lektion(QUANTEN)
    p = tutor.new_profile()
    p["current_task"] = {"konzept": "Superposition"}
    theorie = tutor.generate_theory(lesson, p, [], "konzept")
    history = [{"type": "task", "payload": dict(theorie, typ="theorie")}]
    genauer = tutor.answer_question(lesson, p, {"konzept": "Superposition", "inhalt": theorie.get("inhalt", "")},
                                    "genauer", history, "genauer", 1)
    text = " ".join([theorie.get("inhalt", ""), theorie.get("beispiel", ""), genauer.get("antwort", "")])
    anwendung = re.search(r"(Quantencomputer|Sensor|Anwendung|Beispiel|Logistik|Kryptograf|Messung|Technik)", text, re.I)
    grund = re.search(r"\b(weil|dadurch|deshalb|denn|sodass|so dass|da |darum|damit)\b", text, re.I)
    b.ak("D-03", "AK 4 Superposition: Anwendung mit Begründung (heuristisch, bitte lesen)",
         bool(anwendung and grund), "Anwendung und Begründungswort gefunden" if anwendung and grund else "fehlt")
    b.text(f"\n### Superposition\n\nTheorie:\n\n{zitat(theorie.get('inhalt'), 900)}\n\n"
           f"Beispiel:\n\n{zitat(theorie.get('beispiel'), 900)}\n\nGenauer erklärt:\n\n"
           f"{zitat(genauer.get('antwort'), 900)}\n")


# ---------------------------------------------------------------- D-04

@paket("D-04")
def eval_d04(b: Bericht, anzahl: int):
    """Niveauwunsch im Chat wird erkannt, bestätigt und hält."""
    b.abschnitt("D-04 Niveausteuerung",
                "Der Niveauwunsch wird im Chat geäussert. Neben dem Satz aus dem Auftrag "
                "werden Umschreibungen getestet, die der feste Mustervergleich nicht kennt; dort "
                "zählt allein die Einordnung durch das Modell.")
    c = client()
    saetze = ["Ich möchte auf dem Grundniveau bleiben.",
              "Bitte nicht schwieriger machen, ich bin bei dem Thema noch Anfängerin.",
              "Können wir beim einfachsten Level bleiben?"]
    for i, satz in enumerate(saetze):
        c.post("/api/learner/login", json={"name": f"Eval D04 {i}"})
        sid = c.post("/api/session/start", json={"lesson_id": HAFTUNG, "neu_beginnen": True}).json()["session_id"]
        c.post(f"/api/session/{sid}/assess", json={"answers": [
            "Wer einen Schaden verursacht, muss ihn ersetzen, wenn er schuld ist.",
            "Der Velofahrer haftet, weil er fahrlässig war.",
            "Bei der Kausalhaftung braucht es kein Verschulden."]})
        c.post(f"/api/session/{sid}/niveau", json={"aktion": "festhalten", "level": "intermediate"})
        c.post(f"/api/session/{sid}/niveau", json={"aktion": "automatisch"})
        c.post(f"/api/session/{sid}/next")
        r = c.post(f"/api/session/{sid}/chat", json={"message": satz}).json()
        levels = []
        for _ in range(3):
            t = c.post(f"/api/session/{sid}/next").json()
            if t.get("done"):
                break
            levels.append(t["progress"]["level"])
            if t["task"]["typ"] == "aufgabe":
                c.post(f"/api/session/{sid}/answer", json={"answer": "weiss nicht"})
                c.post(f"/api/session/{sid}/answer", json={"answer": "weiss nicht"})
        events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
        wunsch = [e["payload"] for e in events if e["type"] == "niveau_wunsch"]
        ziel = wunsch[0]["nach"] if wunsch else None
        if i == 0:
            ok = ziel == "basic" and set(levels) <= {"basic"}
            name = "AK 2 Satz aus dem Auftrag: erkannt, bestätigt, bleibt basic"
        else:
            ok = ziel is not None and set(levels) <= {ziel}
            name = f"Umschreibung {i}: erkannt, Niveau bleibt danach gleich"
        b.ak("D-04", name, ok, f"Wunsch → {ziel or 'nicht erkannt'}; Levels danach: {', '.join(levels) or '–'}")
        b.text(f"- «{satz}» → {zitat(r.get('antwort'), 300)[2:]}")


# ---------------------------------------------------------------- D-05

A, K, T, F = "ausgewogen", "korrekt", "teilweise", "falsch"
AUFGABEN_D05 = {
    "hund": (HAFTUNG, {
        "inhalt": "Der Hund von Frau Meier springt über den Gartenzaun und beisst einen Passanten ins Bein.",
        "frage": "Welche Haftung greift hier für Frau Meier?",
        "erwartete_antwort": "Die Tierhalterhaftung nach Art. 56 OR: Frau Meier haftet als Halterin auch ohne eigenes Verschulden.",
        "schluesselbegriffe": ["Tierhalterhaftung"], "konzept": "Tierhalterhaftung"}),
    "velo": (HAFTUNG, {
        "inhalt": "Lena stösst beim Velofahren aus Unaufmerksamkeit einen Fussgänger um, der sich dabei die Hand bricht.",
        "frage": "Haftet Lena nach Art. 41 OR? Begründe deine Antwort.",
        "erwartete_antwort": "Ja: Schaden (Heilungskosten), Widerrechtlichkeit (Körperverletzung), adäquater Kausalzusammenhang und Verschulden (Fahrlässigkeit) liegen vor.",
        "schluesselbegriffe": ["Schaden", "Widerrechtlichkeit", "Kausalzusammenhang", "Verschulden"],
        "konzept": "Verschuldenshaftung"}),
    "pizza": (BRUCH, {
        "inhalt": "Eine Pizza wird in 8 gleich grosse Stücke geteilt. Tim isst 3 Stücke.",
        "frage": "Welcher Bruchteil der Pizza bleibt übrig?",
        "erwartete_antwort": "5/8 der Pizza", "schluesselbegriffe": ["5/8"], "konzept": "Bruchteile"}),
    "nenner": (BRUCH, {
        "inhalt": "Beim Bruch 3/4 steht die 4 unter dem Bruchstrich.",
        "frage": "Was gibt die 4 an?",
        "erwartete_antwort": "Der Nenner gibt an, in wie viele gleich grosse Teile das Ganze geteilt wird.",
        "schluesselbegriffe": ["Nenner", "gleich grosse Teile"], "konzept": "Nenner"}),
    "ort": (QUANTEN, {
        "inhalt": "Eine Forscherin bestimmt den Ort eines Elektrons sehr genau.",
        "frage": "Was folgt daraus für die Bestimmung seines Impulses, und warum?",
        "erwartete_antwort": "Der Impuls lässt sich dann nur sehr ungenau bestimmen, weil Ort und Impuls nach der Heisenbergschen Unschärferelation nicht gleichzeitig beliebig genau messbar sind.",
        "schluesselbegriffe": ["ungenau", "Unschärferelation"], "konzept": "Unschärferelation"}),
    "abhoeren": (QUANTEN, {
        "inhalt": "Eine Bank überträgt Schlüssel mit verschränkten Photonen. Ein Angreifer versucht mitzuhören.",
        "frage": "Warum kann der Abhörversuch erkannt werden?",
        "erwartete_antwort": "Weil das Abhören eine Messung ist, die die Verschränkung bzw. den Zustand der Photonen stört; diese Störung lässt sich nachweisen.",
        "schluesselbegriffe": ["Messung", "Verschränkung", "Störung"], "konzept": "Quantenverschränkung"}),
}
# (Aufgabe, Antwort(en), erlaubte Urteile bei ausgewogen, erlaubte Urteile bei streng, sachlich falsch?)
TESTSET_D05 = [
    ("hund", ["Kausalhaftung"], {T}, {T}, False),                       # Screenshot 4
    ("hund", ["Die Tierhalterhaftung nach Art. 56 OR. Frau Meier haftet als Halterin, auch wenn sie selbst nichts falsch gemacht hat."], {K}, {K}, False),
    ("hund", ["Frau Meier haftet nur, wenn sie den Hund absichtlich auf den Passanten gehetzt hat."], {F}, {F}, True),
    ("hund", ["Die Halterin muss zahlen, auch wenn sie nichts falsch gemacht hat."], {T, K}, {T}, False),
    ("velo", ["Ja. Es gibt einen Schaden (Arztkosten), die Körperverletzung ist widerrechtlich, ihr Stoss hat den Bruch verursacht, und sie war unaufmerksam, also fahrlässig."], {K}, {K, T}, False),
    ("velo", ["Ja, weil sie fahrlässig war."], {T}, {T}, False),
    ("velo", ["Nein, weil sie den Fussgänger nicht absichtlich umgestossen hat."], {F}, {F}, True),
    ("velo", ["Ja, weil sie fahrlässig war.",
              "Dazu kommen der Schaden durch die gebrochene Hand, die widerrechtliche Körperverletzung und dass ihr Stoss den Bruch verursacht hat."], {K, T}, {K, T}, False),
    ("pizza", ["5/8"], {K}, {K}, False),
    ("pizza", ["3/8"], {F}, {F}, True),
    ("pizza", ["Es bleiben 5 Stücke übrig."], {T, F}, {T, F}, False),
    ("nenner", ["Die 4 ist der Nenner und sagt, in wie viele gleich grosse Teile man das Ganze teilt."], {K}, {K}, False),
    ("nenner", ["Die 4 sagt, wie viele Teile man nimmt."], {F}, {F}, True),
    ("ort", ["Der Impuls wird entsprechend ungenau, weil Ort und Impuls nach der Unschärferelation nicht gleichzeitig genau messbar sind."], {K}, {K}, False),
    ("ort", ["Dann ist auch der Impuls sehr genau bekannt."], {F}, {F}, True),
    ("ort", ["Das Messgerät ist einfach zu ungenau für beides."], {F}, {F}, True),
    ("abhoeren", ["Abhören ist eine Messung, und die stört die Verschränkung. Das merken die Empfänger."], {K}, {K, T}, False),
    ("abhoeren", ["Die Verbindung wird unterbrochen."], {T, F}, {T, F}, False),
]


@paket("D-05")
def eval_d05(b: Bericht, anzahl: int):
    """Bewertungsgenauigkeit: Testset mit festgelegten Urteilen, ausgewogen und streng."""
    from app import tutor
    b.abschnitt("D-05 Bewertungsgenauigkeit",
                f"{len(TESTSET_D05)} Antworten zu drei Lektionen mit festgelegtem erwartetem Urteil. "
                "Wo zwei Urteile vertretbar sind, zählen beide als richtig. Jede Antwort wird bei "
                "«ausgewogen» und «streng» bewertet, bei «nachsichtig» nur zur Information.")
    zeilen = ["| Aufgabe | Antwort | erwartet (ausgewogen) | ausgewogen | streng | nachsichtig |",
              "|---|---|---|---|---|---|"]
    treffer = {"ausgewogen": 0, "streng": 0}
    falsch_als_richtig = []
    abweichungen: list[str] = []
    screenshot4 = {}
    for nr, (key, antworten, ok_a, ok_s, sachlich_falsch) in enumerate(TESTSET_D05):
        lid, task = AUFGABEN_D05[key]
        urteile = {}
        for strenge in ("ausgewogen", "streng", "nachsichtig"):
            lesson = dict(lektion(lid), einstellungen={"bewertungsstrenge": strenge})
            vorher = []
            for i, antwort in enumerate(antworten):
                r = tutor.evaluate_answer(lesson, tutor.new_profile(), dict(task, typ="aufgabe"), antwort, vorher)
                vorher.append({"antwort": antwort, "hinweis": r.get("hinweis", "")})
            urteile[strenge] = r
        for strenge, erlaubt in (("ausgewogen", ok_a), ("streng", ok_s)):
            if urteile[strenge]["bewertung"] in erlaubt:
                treffer[strenge] += 1
            else:
                r = urteile[strenge]
                abweichungen.append(
                    f"- {key} ({strenge}): «{antworten[-1]}» → {r['bewertung']}, erwartet "
                    f"{'/'.join(sorted(erlaubt))}. Elemente: "
                    + ("; ".join(f"{e['element']} ({e['status']})" for e in r.get("elemente", [])) or "keine")
                    + (" · Widerspruch" if r.get("sachlicher_widerspruch") else ""))
            if sachlich_falsch and urteile[strenge]["bewertung"] == "korrekt":
                falsch_als_richtig.append((key, antworten[-1], strenge))
        if nr == 0:
            screenshot4 = {s: urteile[s]["bewertung"] for s in ("ausgewogen", "streng")}
        zeilen.append(f"| {key} | {' → '.join(antworten)} | {'/'.join(sorted(ok_a))} | "
                      + " | ".join(urteile[s]["bewertung"] for s in ("ausgewogen", "streng", "nachsichtig")) + " |")
        if nr in (0, 5, 7):
            r = urteile["ausgewogen"]
            b.text(f"\n**Beispiel {key}: «{antworten[-1]}»** – Elemente bei ausgewogen: "
                   + "; ".join(f"{e['element']} ({e['status']})" for e in r.get("elemente", []))
                   + f"\n\nFeedback: {zitat(r.get('feedback'), 400)[2:]}\n")
    b.text("\n" + "\n".join(zeilen))
    if abweichungen:
        b.text("\n### Abweichungen mit Elementen\n\n" + "\n".join(abweichungen))
    n = len(TESTSET_D05)
    b.ak("D-05", "AK 1 mindestens zehn Urteile stimmen (ausgewogen)", treffer["ausgewogen"] >= 10,
         f"ausgewogen {treffer['ausgewogen']}/{n}, streng {treffer['streng']}/{n}")
    b.ak("D-05", "AK 1 keine sachlich falsche Antwort als richtig", not falsch_als_richtig,
         "; ".join(f"{k} ({s})" for k, _, s in falsch_als_richtig) or "keine")
    b.ak("D-05", "AK 2 Screenshot 4 bei ausgewogen und streng teilweise",
         screenshot4 == {"ausgewogen": "teilweise", "streng": "teilweise"}, str(screenshot4))


# ---------------------------------------------------------------- D-06

@paket("D-06")
def eval_d06(b: Bericht, anzahl: int):
    """Material prüfen: Quantenphysik hat Lücken, ein vollständiges Material keine."""
    sys.path.insert(0, str(ROOT / "tests"))
    from test_material_pruefen import VOLLSTAENDIG, VOLLSTAENDIG_ZIELE
    from app import tutor
    b.abschnitt("D-06 Material prüfen")
    q = lektion(QUANTEN)
    r1 = tutor.check_material(q["lernziele"], q["material"])
    r2 = tutor.check_material(VOLLSTAENDIG_ZIELE, VOLLSTAENDIG)
    b.ak("D-06", "AK 1 Quantenphysik-Material: mindestens eine Lücke", r1["luecken"] >= 1, f"{r1['luecken']} Lücken")
    b.ak("D-06", "AK 1 vollständiges Beispielmaterial: keine Lücke", r2["luecken"] == 0, f"{r2['luecken']} Lücken")
    for titel, r in (("Quantenphysik", r1), ("Vollständiges Beispiel", r2)):
        b.text(f"\n### {titel}\n")
        b.text("| Lernziel | Erklärung | Beispiel | Begründung | Hinweis |\n|---|---|---|---|---|")
        for z in r["ziele"]:
            b.text(f"| {z['ziel']} | {z['erklaerung']} | {z['beispiel']} | {z['begruendung']} | {z['hinweis']} |")
        for h in r["hinweise"]:
            b.text(f"\n{h}")


# ---------------------------------------------------------------- Auftrag 2: D-07 bis D-12, T-09

def _halbe_antwort(task: dict, events: list) -> str:
    """Simulierte lernende Person, die nur einen Teil der Lösung nennt."""
    w = (task.get("erwartete_antwort") or "weiss nicht").split()
    return " ".join(w[: max(3, len(w) // 2)])


@paket("D-07")
def eval_d07(b: Bericht, anzahl: int):
    """Nach «teilweise» entscheidet die lernende Person, kein automatisches Weitergehen."""
    b.abschnitt("D-07 Wahl nach teilweise richtiger Antwort",
                "Je eine Sequenz in Quantenphysik und Haftungsrecht. Die simulierte lernende Person "
                "nennt jeweils nur die erste Hälfte der Musterlösung.")
    teilweise, automatisch = 0, []
    for i, lid in enumerate((QUANTEN, HAFTUNG)):
        _, events = sequenz(lid, f"Eval D07 {i}", antwort=_halbe_antwort)
        for e in events:
            p = e["payload"]
            if e["type"] == "answer_evaluated" and p.get("bewertung") == "teilweise":
                teilweise += 1
                if p.get("adaption") != "wahl_teilweise":
                    automatisch.append((lid, p.get("adaption")))
    b.ak("D-07", "AK 1 nach jedem «teilweise» eine Wahl, keine Weiterleitung", not automatisch,
         f"{teilweise} teilweise Antworten, {len(automatisch)} ohne Wahl")


def _theorien(events: list) -> list[tuple[int, dict]]:
    return [(i, e["payload"]) for i, e in enumerate(events)
            if e["type"] == "task" and e["payload"].get("typ") == "theorie"]


@paket("D-08")
def eval_d08(b: Bericht, anzahl: int):
    """Keine zwei aufeinanderfolgenden Theorieschritte mit gleichem Inhalt."""
    from app import didaktik, tutor
    b.abschnitt("D-08 Keine doppelte Theorie",
                "Vier vollständige Sequenzen (je zwei pro Lektion), eine davon mit halben Antworten. "
                "Verglichen werden aufeinanderfolgende Theorieschritte (ohne Aufgabe dazwischen) und "
                "automatische Theorien zu bereits erklärten Konzepten.")
    doppelt, uebersprungen, gesamt = [], 0, 0
    for i, lid in enumerate((QUANTEN, HAFTUNG, QUANTEN, HAFTUNG)):
        _, events = sequenz(lid, f"Eval D08 {i}", antwort=_halbe_antwort if i >= 2 else None)
        uebersprungen += sum(1 for e in events if e["type"] == "theorie_uebersprungen")
        theorien = _theorien(events)
        gesamt += len(theorien)
        for (ia, a), (ib, t) in zip(theorien, theorien[1:]):
            dazwischen = [e for e in events[ia + 1:ib] if e["type"] == "task" and e["payload"].get("typ") == "aufgabe"]
            if dazwischen or t.get("nochmals_anders"):
                continue
            w = didaktik.aehnlichkeit(didaktik.theorietext(t), [didaktik.theorietext(a)])
            if w >= didaktik.THEORIE_AEHNLICH or didaktik.gleiches_konzept(a.get("konzept"), t.get("konzept")):
                doppelt.append((lid, a, t, w))
    b.ak("D-08", "AK 4 keine zwei aufeinanderfolgenden Theorien mit gleichem Inhalt", not doppelt,
         f"{len(doppelt)} Paare bei {gesamt} Theorien, {uebersprungen} Theorien übersprungen")
    for lid, a, t, w in doppelt:
        b.text(f"- {lid}: «{a.get('titel')}» → «{t.get('titel')}» (Ähnlichkeit {round(w * 100)} %)")


@paket("D-09")
def eval_d09(b: Bericht, anzahl: int):
    """Jede Aufgabe direkt nach einer Theorie passt zu dieser Theorie."""
    from app import didaktik, tutor
    b.abschnitt("D-09 Aufgabe passt zur vorangehenden Theorie",
                f"Pro Lektion {anzahl} Paare aus Theorie und unmittelbar folgender Aufgabe.")
    zeilen = ["| Lektion | Theorie (Konzept) | Aufgabe (Konzept) | Frage | passt |", "|---|---|---|---|---|"]
    fehler = 0
    for lid in (QUANTEN, HAFTUNG):
        lesson = lektion(lid)
        konzepte: list[str] = []
        for _ in range(anzahl):
            p = dict(tutor.new_profile(), level="intermediate", covered=list(konzepte), erklaert=list(konzepte))
            theorie = tutor.generate_theory(lesson, p, [])
            if theorie.get("_fallback"):
                continue
            konzepte.append(theorie.get("konzept", ""))
            history = [{"type": "task", "payload": theorie}]
            p.update(covered=list(konzepte), erklaert=list(konzepte), last_type="theorie")
            task = tutor.generate_task(lesson, p, history)
            if task.get("_fallback"):
                continue
            v = (didaktik.aufgabe_passt_zur_theorie(task, theorie)
                 or didaktik.begriff_nicht_erklaert(task, didaktik.theorietext(theorie), lesson))
            fehler += bool(v)
            zeilen.append(f"| {lid} | {theorie.get('titel')} ({theorie.get('konzept')}) | {task.get('titel')} "
                          f"({task.get('konzept')}) | {task.get('frage')} | {'ja' if not v else 'nein: ' + v[:80]} |")
    b.text("\n".join(zeilen))
    b.ak("D-09", "AK 3 jede Aufgabe direkt nach einer Theorie passt dazu (pro Fall im Bericht)", fehler == 0,
         f"{fehler} Abweichungen")


@paket("D-10")
def eval_d10(b: Bericht, anzahl: int):
    """Frage nennt alle erwarteten Elemente, die Bewertung verlangt nichts darüber hinaus."""
    from app import didaktik, tutor
    b.abschnitt("D-10 Erwartete Elemente",
                f"{anzahl} Aufgaben aus der Haftungsrecht-Lektion, jede mit einer halben Antwort bewertet.")
    lesson = lektion(HAFTUNG)
    ohne, einteilig, abweichend, zeilen = 0, 0, 0, []
    for i in range(anzahl):
        p = dict(tutor.new_profile(), level=tutor.LEVELS[i % 3])
        task = tutor.generate_task(dict(lesson, einstellungen={"einsatzart": "vertiefung"}), p, [])
        if task.get("_fallback"):
            continue
        el = didaktik.elemente_bereinigen(task.get("erwartete_elemente"))   # seit D-14 Objekte {dimension, erwartet}
        ohne += not el
        einteilig += bool(didaktik.elemente_passen_zur_frage(task))
        r = tutor.evaluate_answer(lesson, p, task, _halbe_antwort(task, []))
        verwendet = [e["element"] for e in r.get("elemente", [])]
        abweichend += verwendet != el
        zeilen.append(f"- «{task.get('frage')}» – Elemente: {'; '.join(el)} – Bewertung: {r.get('bewertung')} "
                      f"({'gespeicherte Elemente' if verwendet == el else 'abweichend: ' + '; '.join(verwendet)})")
    b.text("\n".join(zeilen))
    b.ak("D-10", "AK 1 jede Aufgabe hat erwartete Elemente", ohne == 0, f"{ohne} ohne")
    b.ak("D-10", "AK 4 kein Element, das die Frage nicht nennt (Regel und Bewertung)",
         einteilig == 0 and abweichend == 0, f"{einteilig} einteilige Fragen mit mehreren Elementen, "
                                             f"{abweichend} Bewertungen mit anderen Elementen")


@paket("D-11")
def eval_d11(b: Bericht, anzahl: int):
    """Kopierte Theorie wird erkannt, eigene Formulierungen nicht."""
    from app import didaktik, tutor
    b.abschnitt("D-11 Kopierte Antworten")
    erkannt, falsch_positiv = 0, 0
    for lid in (QUANTEN, HAFTUNG):
        lesson = lektion(lid)
        theorie = tutor.generate_theory(lesson, tutor.new_profile(), [])
        quellen = tutor.kopie_quellen(lesson, [{"type": "task", "payload": theorie}])
        erkannt += didaktik.kopie_pruefen(theorie.get("inhalt", ""), quellen)["anteil"] >= didaktik.KOPIE_SCHWELLE
        eigen = tutor.answer_question(lesson, tutor.new_profile(), None,
                                      "Formuliere die Erklärung als kurze Antwort einer lernenden Person in ganz "
                                      "eigenen Worten, ohne Sätze aus dem Text zu übernehmen.", [])
        k = didaktik.kopie_pruefen(eigen.get("antwort", ""), quellen)
        falsch_positiv += k["anteil"] >= didaktik.KOPIE_SCHWELLE
        b.text(f"- {lid}: Kopie der Theorie erkannt; Umformulierung {round(k['anteil'] * 100)} % übernommen")
    b.ak("D-11", "AK 1/3 kopierte Theorie erkannt", erkannt == 2, f"{erkannt} von 2")
    b.ak("D-11", "AK 2 Umformulierung nicht als Kopie", falsch_positiv == 0, f"{falsch_positiv} von 2")


@paket("D-12")
def eval_d12(b: Bericht, anzahl: int):
    """Urteil und Bewertungstext passen zusammen."""
    from app import didaktik, tutor
    b.abschnitt("D-12 Urteil und Bewertungstext", "Das D-05-Testset bei «ausgewogen».")
    widersprueche = []
    for key, antworten, *_ in TESTSET_D05:
        lid, task = AUFGABEN_D05[key]
        r = tutor.evaluate_answer(lektion(lid), tutor.new_profile(), dict(task, typ="aufgabe"), antworten[-1])
        v = didaktik.urteil_widerspricht_text(r)
        if v:
            widersprueche.append(f"- {key}: «{antworten[-1]}» → {r['bewertung']}: {zitat(r.get('feedback'), 200)[2:]}")
    b.ak("D-12", "Ergänzung: kein Widerspruch zwischen Urteil und Text", not widersprueche,
         f"{len(widersprueche)} von {len(TESTSET_D05)}")
    b.text("\n".join(widersprueche))


@paket("T-09")
def eval_t09(b: Bericht, anzahl: int):
    """Fallbacks und leere Antworten über den ganzen bisherigen Lauf."""
    from app import llm
    b.abschnitt("T-09 Fallbacks und leere Antworten",
                "Zusammenfassung aller LLM-Aufrufe dieses Evaluationslaufs (bitte als letztes Paket "
                "ausführen). Vergleich mit der Messübersicht vom 29.9.2026.")
    leer = sum(1 for t in llm.timings() if t.get("fehler") == "leere Antwort")
    b.text("| Schritt | Aufrufe | Fehler | Fallbacks | grösster Prompt (geschätzt) |\n|---|---|---|---|---|")
    for z in llm.timing_summary():
        b.text(f"| {z['schritt']} | {z['anzahl']} | {z['fehler']} | {z['fallbacks']} | "
               f"{z.get('max_prompt_tokens_geschaetzt') or '–'} |")
    gesamt = sum(z["anzahl"] for z in llm.timing_summary())
    fb = len(llm.fallbacks())
    b.ak("T-09", "AK 4 Fallbacks (Information)", True, f"{fb} Fallbacks, {leer} leere Antworten bei {gesamt} Aufrufen")


# ---------------------------------------------------------------- Auftrag 3: D-13 bis D-18
#
# Die Fälle aus Anhang B des Auftrags stehen wörtlich hier, auch mit
# Tippfehlern. Aufgabe, Musterlösung und Antworten sind fest vorgegeben,
# damit das Ergebnis nicht von der Aufgabengenerierung abhängt. Wo die
# damalige Musterlösung nicht bekannt ist (its.db vom 13.10.2026 lag nicht
# vor), ist die im Feedback sichtbare bzw. eine naheliegende Fassung
# eingesetzt und im Feld «quelle» vermerkt.

FALL1 = {
    "typ": "aufgabe", "titel": "Unfall auf dem Spielplatz", "konzept": "Werkeigentümerhaftung",
    "inhalt": "Ein Kind spielt auf einem Spielplatz. Während des Spiels bricht eine Schaukel ab und das Kind "
              "verletzt sich. Der Spielplatz wird von einer Stadtverwaltung betrieben.",
    "frage": "Wer ist für den Schaden verantwortlich und welche Art der Haftung greift hier?",
    "erwartete_antwort": "Die Stadt ist als Werkeigentümerin verantwortlich; es greift die Werkeigentümerhaftung, "
                         "eine Kausalhaftung.",
    "erwartete_elemente": [{"dimension": "verantwortliche Person", "erwartet": "die Stadt als Betreiberin des Spielplatzes"},
                           {"dimension": "Art der Haftung", "erwartet": "Werkeigentümerhaftung, eine Kausalhaftung"}],
    "quelle": "Musterlösung eingesetzt (Haftung der Stadt laut Christian wahrscheinlich)",
}
FALL1_ANTWORT = "Hersteller der Schaukel Produktehaftpflicht"
FALL1_NACHFRAGE = "Wieso könnte dies nicht auch ein Fall von Produktehaftpflicht sein?"

FALL2 = {
    "typ": "aufgabe", "titel": "Tierhalterhaftung im Alltag", "konzept": "Tierhalterhaftung",
    "inhalt": "Ein Junge spielt mit einem Ball im Park. Der Ball rollt in einen Zaun und zerbricht eine "
              "Fensterscheibe eines nahegelegenen Hauses. Der Besitzer des Hauses will Schadenersatz von dem "
              "Jungen verlangen.",
    "frage": "Wer ist verantwortlich für den Schaden und welche Art der Haftung greift hier?",
    "erwartete_antwort": "Verantwortlich ist der Junge bzw. seine Eltern; es handelt sich um eine Kausalhaftung.",
    "erwartete_elemente": [{"dimension": "verantwortliche Person", "erwartet": "der Junge"},
                           {"dimension": "Art der Haftung", "erwartet": "Kausalhaftung"}],
    "quelle": "damalige Musterlösung aus der Bewertung im Screenshot abgeleitet («nicht Verschuldenshaftung, "
              "sondern Kausalhaftung»)",
}
FALL2_KORRIGIERT = dict(FALL2, titel="Glasbruch im Park", konzept="Verschuldenshaftung",
                        erwartete_antwort="Der Junge haftet nach Art. 41 OR (Verschuldenshaftung), wenn er "
                                          "urteilsfähig ist; die Eltern nur bei verletzter Aufsichtspflicht.",
                        erwartete_elemente=[{"dimension": "verantwortliche Person", "erwartet": "der Junge"},
                                            {"dimension": "Art der Haftung", "erwartet": "Verschuldenshaftung nach Art. 41 OR"}])
FALL2_ANTWORT = "Verschuldenshaftung. Verantwortlich ist der Junge, bzw. bei Minderjährigkeit seine Eltewn."
FALL2_BEWERTUNG = "Es geht hier nicht um Verschuldenshaftung, sondern um Kausalhaftung."
FALL2_NACHFRAGE = "Wieso handelt es sich hier um Kausalhaftung?"

FALL3 = {
    "typ": "aufgabe", "titel": "Schaukel im Vereinsspielplatz", "konzept": "Werkeigentümerhaftung",
    "inhalt": "Ein Kind spielt auf einem Spielplatz. Während des Spiels bricht ein Teil der Schaukel aus. Das Kind "
              "verletzt sich leicht. Der Spielplatz gehört einem Verein, der für die Wartung und Sicherheit "
              "verantwortlich ist.",
    "frage": "Welche Voraussetzung ist hier am stärksten erkennbar und warum?",
    "erwartete_antwort": "Die Verantwortung des Vereins für Wartung und Sicherheit; ein mangelhafter Unterhalt der "
                         "Schaukel ist naheliegend.",
    "erwartete_elemente": [{"dimension": "Voraussetzung mit Begründung",
                            "erwartet": "Verantwortung des Spielplatzbetreibers für Wartung und Sicherheit"}],
    "musterloesung_pruefung": {"ergebnis": "uebereinstimmend",
                               "offene_punkte": ["ob die Wartung der Schaukel vernachlässigt wurde"]},
    "quelle": "Musterlösung eingesetzt",
}
FALL3_A = ("Verantwortung des Spielplatzbetreibers / weil dieser für Sicherheit und Wartung zuständig ist / "
           "Vermutlich führte mangelnde Wartung der Schaukel zum Schaden.")
FALL3_B = ("Verantwortung des Spielplatzbetreibers / weil dieser für Sicherheit und Wartung zuständig ist / "
           "Mangelnde Wartung der Schaukel verursachte den Schaden.")

FALL4 = {
    "typ": "aufgabe", "titel": "Zusammenstoss auf dem Schulhof", "konzept": "Kausalhaftung",
    "inhalt": "Ein Schüler fährt mit seinem Fahrrad auf dem Schulhof. Er biegt plötzlich ab, um einem Ball "
              "auszuweichen und prallt gegen einen anderen Schüler. Der andere Schüler stürzt und verletzt sich "
              "leicht. Die Schule ist für die Sicherheit auf dem Schulhof verantwortlich.",
    "frage": "Nenne die verantwortliche Person und die Art der Haftung, die hier greift.",
    "erwartete_antwort": "Die Schule ist verantwortlich, weil sie für die Sicherheit auf dem Schulhof sorgt. Es "
                         "handelt sich um eine Form der Kausalhaftung.",
    "erwartete_elemente": [{"dimension": "verantwortliche Person",
                            "erwartet": "die Schule, weil sie für die Sicherheit auf dem Schulhof sorgt"},
                           {"dimension": "Art der Haftung", "erwartet": "Kausalhaftung"}],
    "quelle": "Musterlösung aus dem Feedback (sichtbar nach «Lösung ansehen»)",
}
FALL4_VERSUCHE = [
    "Der Schüler bzw. seine Eltern. Motorfahrzeughalterhaftung",
    "Kausalhaftung, Schule ist für Sicherheit auf dem Schulhof verantwortlich",
    "Kausalhaftung, Schule ist für Sicherheit auf dem Schulhof verantwortlich und daher haftbar",
    "Kausalhaftung, Schule ist haftbar",
    "Kausalhaftung, Schule ist haftbar, weil sie für die Sicherheit verantwortlich ist.",
]

QUANTEN_SUPER = {
    "typ": "aufgabe", "titel": "Die unentschiedene Münze", "konzept": "Superposition",
    "inhalt": "Ein Quantenobjekt kann vor einer Messung in zwei Zuständen zugleich sein, ähnlich einer Münze, die "
              "sich noch dreht.",
    "frage": "Was bedeutet Superposition für das Quantenobjekt vor der Messung?",
    "erwartete_antwort": "Es befindet sich in einer Überlagerung mehrerer Zustände; erst die Messung legt einen fest.",
    "erwartete_elemente": [{"dimension": "Bedeutung der Superposition",
                            "erwartet": "Überlagerung mehrerer Zustände bis zur Messung"}]}

# Gegenprobe (D-15 AK 2): klar falsche Antworten, die «falsch» bleiben müssen
GEGENPROBE = [
    ("Fall 4, Versuch 1", HAFTUNG, FALL4, FALL4_VERSUCHE[0]),
    ("Fall 1, Fahrzeug", HAFTUNG, FALL1, "Der Autofahrer haftet aus Motorfahrzeughalterhaftung."),
    ("Fall 2, Tier", HAFTUNG, FALL2_KORRIGIERT, "Der Hausbesitzer haftet als Tierhalter nach Art. 56 OR."),
    ("hund, Absicht", HAFTUNG, AUFGABEN_D05["hund"][1],
     "Frau Meier haftet nur, wenn sie den Hund absichtlich auf den Passanten gehetzt hat."),
    ("velo, Absicht", HAFTUNG, AUFGABEN_D05["velo"][1],
     "Nein, weil sie den Fussgänger nicht absichtlich umgestossen hat."),
    ("ort, Impuls genau", QUANTEN, AUFGABEN_D05["ort"][1], "Dann ist auch der Impuls sehr genau bekannt."),
    ("ort, Messgerät", QUANTEN, AUFGABEN_D05["ort"][1], "Das Messgerät ist einfach zu ungenau für beides."),
    ("Superposition, Springen", QUANTEN, QUANTEN_SUPER,
     "Das Objekt springt sehr schnell zwischen den beiden Zuständen hin und her."),
    ("Superposition, Ort", QUANTEN, QUANTEN_SUPER, "Superposition heisst, dass das Objekt an einem festen Ort ruht."),
    ("abhoeren, Lautstärke", QUANTEN, AUFGABEN_D05["abhoeren"][1],
     "Weil der Angreifer beim Mithören Geräusche macht, die man hört."),
]

# D-16 AK 2: Paare, die sich nur in der Abschwächung unterscheiden
VORSICHT_PAARE = [
    (HAFTUNG, FALL3, FALL3_A, FALL3_B),
    (HAFTUNG, AUFGABEN_D05["hund"][1],
     "Frau Meier haftet vermutlich als Halterin nach Art. 56 OR, auch ohne eigenes Verschulden.",
     "Frau Meier haftet als Halterin nach Art. 56 OR, auch ohne eigenes Verschulden."),
    (HAFTUNG, AUFGABEN_D05["velo"][1],
     "Ja, wahrscheinlich: Schaden, Widerrechtlichkeit, Kausalzusammenhang und Fahrlässigkeit liegen vor.",
     "Ja: Schaden, Widerrechtlichkeit, Kausalzusammenhang und Fahrlässigkeit liegen vor."),
    (QUANTEN, AUFGABEN_D05["ort"][1],
     "Der Impuls ist vermutlich nur ungenau bestimmbar, weil Ort und Impuls nach der Unschärferelation nicht "
     "gleichzeitig genau messbar sind.",
     "Der Impuls ist nur ungenau bestimmbar, weil Ort und Impuls nach der Unschärferelation nicht gleichzeitig "
     "genau messbar sind."),
    (QUANTEN, AUFGABEN_D05["abhoeren"][1],
     "Wahrscheinlich, weil das Abhören eine Messung ist, die die Verschränkung stört.",
     "Weil das Abhören eine Messung ist, die die Verschränkung stört."),
    (QUANTEN, QUANTEN_SUPER,
     "Es ist vermutlich in einer Überlagerung beider Zustände, bis die Messung einen festlegt.",
     "Es ist in einer Überlagerung beider Zustände, bis die Messung einen festlegt."),
]

NACHFRAGEN_D15 = [
    (FALL1, FALL1_ANTWORT, FALL1_NACHFRAGE),
    (FALL1, "Die Stadt, Werkeigentümerhaftung", "Was wäre, wenn das Kind die Schaukel selbst beschädigt hätte?"),
    (FALL3, FALL3_A, "Könnte nicht auch der Hersteller der Schaukel haften?"),
    (FALL4, FALL4_VERSUCHE[1], "Könnte nicht auch der Schüler auf dem Fahrrad selbst haften?"),
    (FALL2_KORRIGIERT, FALL2_ANTWORT, "Haften nicht immer die Eltern, wenn ein Kind etwas kaputt macht?"),
]


def _el(r: dict) -> str:
    return "; ".join(f"{e.get('element')} ({e.get('status')}{', Annahme: ' + e['annahme'] if e.get('annahme') else ''})"
                     for e in r.get("elemente", [])) or "keine"


@paket("D-13")
def eval_d13(b: Bericht, anzahl: int):
    """Fall, Titel und Musterlösung stimmen überein; Gegenprüfung mit Übereinstimmungsquote."""
    from app import didaktik, llm, tutor
    n = max(20, 2 * anzahl)
    b.abschnitt("D-13 Stimmige Aufgaben",
                f"{n} Paare aus Theorie und unmittelbar folgender Aufgabe aus «{HAFTUNG}», jede Aufgabe mit "
                "Gegenprüfung der Musterlösung. Dazu die festen Regressionsfälle aus Anhang B.")
    lesson = lektion(HAFTUNG)
    fach = didaktik.fachvokabular(lesson)
    zeilen = ["| Theorie | Aufgabe (Titel) | Merkmale im Fall | Titel neutral | Gegenprüfung |", "|---|---|---|---|---|"]
    ohne_merkmal, titel_verraet, ergebnisse = 0, 0, []
    start = len(llm.timings())
    konzepte: list[str] = []
    for i in range(n):
        p = dict(tutor.new_profile(), level=tutor.LEVELS[i % 3], covered=list(konzepte), erklaert=list(konzepte))
        theorie = tutor.generate_theory(lesson, p, [])
        if theorie.get("_fallback"):
            continue
        konzepte.append(theorie.get("konzept", ""))
        p.update(covered=list(konzepte), erklaert=list(konzepte), last_type="theorie")
        task = tutor.generate_task(lesson, p, [{"type": "task", "payload": theorie}])
        if task.get("_fallback"):
            continue
        m = didaktik.merkmale_fehlen_im_fall(task, theorie)
        t = didaktik.loesungswort_in_titel(task, fach)
        ohne_merkmal += bool(m)
        titel_verraet += bool(t)
        erg = (task.get("musterloesung_pruefung") or {}).get("ergebnis", "nicht_geprueft")
        ergebnisse.append(erg)
        zeilen.append(f"| {theorie.get('konzept')} ({', '.join(theorie.get('merkmale') or [])}) | {task.get('titel')} | "
                      f"{'ja' if not m else 'nein'} | {'ja' if not t else 'nein'} | {tutor.GEGENPRUEFUNG_TEXTE.get(erg, erg)} |")
    b.text("\n".join(zeilen))
    geprueft = [e for e in ergebnisse if e != "nicht_geprueft"]
    gut = [e for e in geprueft if e in ("uebereinstimmend", "nach_neugenerierung")]
    quote = len(gut) / len(geprueft) if geprueft else 0.0
    b.ak("D-13", "AK 4 jeder Fall enthält die Merkmale seines Konzepts", ohne_merkmal == 0,
         f"{ohne_merkmal} von {len(ergebnisse)} ohne Merkmal")
    b.ak("D-13", "AK 4 kein Titel nennt die gesuchte Lösung", titel_verraet == 0, f"{titel_verraet} von {len(ergebnisse)}")
    b.ak("D-13", "AK 4 Übereinstimmungsquote der Gegenprüfung mindestens 90 Prozent", quote >= 0.9,
         f"{round(quote * 100)} % ({ergebnisse.count('uebereinstimmend')} direkt, "
         f"{ergebnisse.count('nach_neugenerierung')} nach Neugenerierung, {ergebnisse.count('unsicher')} unsicher, "
         f"{ergebnisse.count('nicht_geprueft')} nicht geprüft)")
    zeiten = [t for t in llm.timings()[start:] if t.get("schritt") in ("MUSTERLOESUNG_PRUEFEN", "MUSTERLOESUNG_VERGLEICHEN")]
    aufgaben = [t for t in llm.timings()[start:] if t.get("schritt") == "NAECHSTE_AUFGABE"]
    extra = sum(t.get("sekunden", 0) for t in zeiten) / max(1, len(ergebnisse))
    b.ak("D-13", "AK 5 zusätzliche Rechenzeit pro Aufgabe (Information)", True,
         f"{round(extra, 1)} s für {len(zeiten)} Prüfaufrufe, Aufgabe selbst im Mittel "
         f"{round(sum(t.get('sekunden', 0) for t in aufgaben) / max(1, len(aufgaben)), 1)} s pro Aufruf")
    # Regressionsfälle aus Anhang B
    r1 = didaktik.loesungswort_in_titel(dict(FALL1, titel="Kausalhaftung beim Spielplatz",
                                             schluesselbegriffe=["Kausalhaftung"]), fach)
    b.ak("D-13", "Fall 1: Titel «Kausalhaftung beim Spielplatz» wird beanstandet", bool(r1), (r1 or "")[:80])
    theorie_tier = {"konzept": "Tierhalterhaftung", "merkmale": ["Tier", "Halter"]}
    r2 = didaktik.merkmale_fehlen_im_fall(dict(FALL2, merkmale=[]), theorie_tier)
    b.ak("D-13", "Fall 2: Fall ohne Tier nach der Tierhalterhaftung wird beanstandet", bool(r2), (r2 or "")[:80])
    g4 = tutor.pruefe_musterloesung(lesson, FALL4)
    b.ak("D-13", "Fall 4: Ergebnis der Gegenprüfung (Information, erwartet abweichend)", True,
         f"{g4['ergebnis']}: {g4.get('loesung', '')[:120]} · offene Punkte: {'; '.join(g4.get('offene_punkte') or [])}")
    g2 = tutor.pruefe_musterloesung(lesson, FALL2)
    b.ak("D-13", "Fall 2: Gegenprüfung der damaligen Musterlösung (Information, erwartet abweichend)", True,
         f"{g2['ergebnis']}: {g2.get('loesung', '')[:120]}")


@paket("D-14")
def eval_d14(b: Bericht, anzahl: int):
    """Regressionsfall 4: Ab Versuch 2 korrekt, Versuch 1 wirkt nicht nach, Hinweise wiederholen sich nicht."""
    from app import didaktik, tutor
    lesson = lektion(HAFTUNG)
    b.abschnitt("D-14 Faire Bewertung von Nachbesserungen",
                f"Fall 4 aus Anhang B mit der damaligen Musterlösung ({FALL4['quelle']}), fünf Versuche nacheinander.")
    vorher, urteile, hinweise = [], [], []
    for i, text in enumerate(FALL4_VERSUCHE, 1):
        r = tutor.evaluate_answer(lesson, tutor.new_profile(), FALL4, text, list(vorher))
        urteile.append(r["bewertung"])
        hinweise.append(r.get("hinweis", ""))
        b.text(f"- Versuch {i}: «{text}» → **{r['bewertung']}** · {_el(r)}\n  Feedback: {zitat(r.get('feedback'), 300)[2:]}"
               + (f"\n  Hinweis: {r.get('hinweis')}" if r.get("hinweis") else ""))
        vorher.append({"antwort": text, "bewertung": r["bewertung"], "hinweis": r.get("hinweis", ""),
                       "elemente": r.get("elemente", [])})
        if r["bewertung"] == "korrekt":
            break
    b.ak("D-14", "AK 2 ab Versuch 2 korrekt, Versuch 1 wirkt nicht nach",
         len(urteile) >= 2 and urteile[1] == "korrekt", " → ".join(urteile))
    gleich = [i for i in range(1, len(hinweise)) if hinweise[i] and hinweise[i - 1]
              and didaktik.hinweis_wiederholt(hinweise[i], [hinweise[i - 1]])]
    b.ak("D-14", "AK 4 keine zwei aufeinanderfolgenden Hinweise fast gleich", not gleich, f"{len(gleich)} Wiederholungen")


@paket("D-15")
def eval_d15(b: Bericht, anzahl: int):
    """Vertretbare Alternativen, Gegenprobe mit klar falschen Antworten, Nachfragen ohne erfundene Angaben."""
    from app import tutor
    b.abschnitt("D-15 Vertretbare Alternativen und Nichtwissen")
    mit_wissen = dict(lektion(HAFTUNG), einstellungen={"wissensstufen": ["material", "allgemeinwissen"]})
    nur_material = dict(lektion(HAFTUNG), einstellungen={"wissensstufen": ["material"]})
    r = tutor.evaluate_answer(mit_wissen, tutor.new_profile(), FALL1, FALL1_ANTWORT)
    annahme = any(e.get("annahme") for e in r.get("elemente", [])) or any(
        w in (r.get("feedback") or "").lower() for w in ("wenn ", "falls ", "sofern ", "annahme"))
    b.text(f"**Fall 1** «{FALL1_ANTWORT}» (Allgemeinwissen erlaubt) → {r['bewertung']} · {_el(r)}\n\n"
           f"Feedback: {zitat(r.get('feedback'), 500)[2:]}\n")
    b.ak("D-15", "AK 1 Fall 1 nicht «falsch», Rückmeldung nennt die Annahme",
         r["bewertung"] != "falsch" and annahme, f"{r['bewertung']}, Annahme genannt: {annahme}")
    r3 = tutor.evaluate_answer(nur_material, tutor.new_profile(), FALL1, FALL1_ANTWORT)
    nb = any(e.get("status") == "nicht_beurteilbar" for e in r3.get("elemente", []))
    b.text(f"**Fall 1 nur Material** → {r3['bewertung']} · {_el(r3)}\n\nFeedback: {zitat(r3.get('feedback'), 400)[2:]}\n")
    b.ak("D-15", "AK 3 nur Material: «nicht beurteilbar», nie «falsch»", r3["bewertung"] != "falsch" and nb,
         f"{r3['bewertung']}, nicht beurteilbar: {nb}")
    zeilen, bleiben = ["| Fall | Antwort | Urteil | Elemente |", "|---|---|---|---|"], 0
    for name, lid, task, antwort in GEGENPROBE:
        g = tutor.evaluate_answer(lektion(lid), tutor.new_profile(), dict(task, typ="aufgabe"), antwort)
        bleiben += g["bewertung"] == "falsch"
        zeilen.append(f"| {name} | {antwort} | {g['bewertung']} | {_el(g)} |")
    b.text("\n**Gegenprobe**\n\n" + "\n".join(zeilen))
    quote = bleiben / len(GEGENPROBE)
    b.ak("D-15", "AK 2 Gegenprobe: mindestens 90 Prozent der klar falschen Antworten bleiben «falsch»",
         quote >= 0.9, f"{bleiben} von {len(GEGENPROBE)} ({round(quote * 100)} %)")
    b.text("\n**Nachfragen (von Hand zu beurteilen: keine erfundenen Angaben zum Sachverhalt?)**\n")
    for task, antwort, frage in NACHFRAGEN_D15:
        bew = tutor.evaluate_answer(mit_wissen, tutor.new_profile(), task, antwort)
        history = [{"type": "task", "payload": task}, {"type": "answer_evaluated", "payload": bew}]
        a = tutor.answer_question(mit_wissen, dict(tutor.new_profile(), wartet_auf="antwort"), task, frage, history)
        b.text(f"- Fall «{task['titel']}», Antwort «{antwort}» ({bew['bewertung']}), Nachfrage «{frage}»\n"
               f"  {zitat(a.get('antwort'), 600)}\n  Beurteilung von Hand: ☐ ohne erfundene Angaben ☐ Alternative ernsthaft geprüft")
    b.ak("D-15", "AK 6 fünf Nachfragen dokumentiert (Beurteilung von Hand)", True, f"{len(NACHFRAGEN_D15)} Nachfragen")


@paket("D-16")
def eval_d16(b: Bericht, anzahl: int):
    """Vorsichtige Formulierungen: Paare mit und ohne Abschwächung erhalten dasselbe Urteil."""
    from app import tutor
    b.abschnitt("D-16 Vorsichtige Formulierungen", "Fall 3 aus Anhang B und fünf weitere Paare.")
    zeilen, gleich = ["| Aufgabe | mit Abschwächung | ohne | gleich |", "|---|---|---|---|"], 0
    for i, (lid, task, a, b_) in enumerate(VORSICHT_PAARE):
        ra = tutor.evaluate_answer(lektion(lid), tutor.new_profile(), dict(task, typ="aufgabe"), a)
        rb = tutor.evaluate_answer(lektion(lid), tutor.new_profile(), dict(task, typ="aufgabe"), b_)
        ok = ra["bewertung"] == rb["bewertung"]
        gleich += ok
        zeilen.append(f"| {task.get('titel') or task.get('frage')} | {ra['bewertung']} | {rb['bewertung']} | {'ja' if ok else 'nein'} |")
        if i == 0:
            b.ak("D-16", "AK 1 Fall 3: A und B erhalten dasselbe Urteil", ok, f"A {ra['bewertung']}, B {rb['bewertung']}")
            b.text(f"Fall 3, Feedback zu A: {zitat(ra.get('feedback'), 400)[2:]}\n")
    b.text("\n".join(zeilen))
    b.ak("D-16", "AK 2 mindestens sechs Paare mit gleichem Urteil", gleich == len(VORSICHT_PAARE) and gleich >= 6,
         f"{gleich} von {len(VORSICHT_PAARE)}")


@paket("D-17")
def eval_d17(b: Bericht, anzahl: int):
    """Regressionsfall 4: Übereinstimmung von Antwort und Lösung wird erkannt."""
    from app import didaktik
    b.abschnitt("D-17 Lösung ansehen", "Deterministischer Abgleich der Versuche aus Fall 4 mit den erwarteten Inhalten.")
    deckt = [didaktik.antwort_deckt_loesung(v, FALL4["erwartete_elemente"]) for v in FALL4_VERSUCHE]
    b.text("\n".join(f"- Versuch {i}: «{v}» → {'stimmt überein' if d else 'weicht ab'}"
                     for i, (v, d) in enumerate(zip(FALL4_VERSUCHE, deckt), 1)))
    b.ak("D-17", "AK 2 Fall 4: Übereinstimmung ab Versuch 2 erkannt, Versuch 1 nicht", deckt[1:] == [True] * 4 and not deckt[0],
         " ".join("ja" if d else "nein" for d in deckt))


@paket("D-18")
def eval_d18(b: Bericht, anzahl: int):
    """Regressionsfall 2: Die Chat-Antwort widerspricht der Bewertung nicht stillschweigend."""
    from app import didaktik, tutor
    b.abschnitt("D-18 Keine widersprüchlichen Aussagen",
                "Fall 2 aus Anhang B: Die damalige Bewertung steht als Verlauf vor der Nachfrage.")
    lesson = lektion(HAFTUNG)
    bewertung = {"bewertung": "falsch", "feedback": FALL2_BEWERTUNG, "hinweis": "",
                 "elemente": [{"element": "verantwortliche Person", "status": "ungenau"},
                              {"element": "Art der Haftung", "status": "falsch"}]}
    history = [{"type": "task", "payload": FALL2}, {"type": "answer_evaluated", "payload": bewertung}]
    a = tutor.answer_question(lesson, dict(tutor.new_profile(), wartet_auf="antwort"), FALL2, FALL2_NACHFRAGE, history)
    still = bool(didaktik.gegensatz_zur_bewertung(FALL2_BEWERTUNG, a.get("antwort", ""))) and not a.get("widerspricht_bewertung")
    b.text(f"Nachfrage «{FALL2_NACHFRAGE}»\n\n{zitat(a.get('antwort'), 700)}\n\n"
           f"widerspricht_bewertung: {a.get('widerspricht_bewertung')}, Irrtum benannt: "
           f"{didaktik.irrtum_benannt(a.get('antwort', ''))}\n")
    b.ak("D-18", "AK 1 Chat-Antwort konsistent oder Irrtum ausdrücklich gekennzeichnet", not still,
         "gekennzeichnet" if a.get("widerspricht_bewertung") else "konsistent" if not still else "stiller Widerspruch")
    r = tutor.evaluate_answer(lesson, tutor.new_profile(), FALL2_KORRIGIERT, FALL2_ANTWORT)
    art = next((e for e in r.get("elemente", []) if "Haftung" in e.get("element", "")), {})
    b.ak("D-18", "Fall 2 als fester Testfall: Verschuldenshaftung korrekt, Eltern höchstens ungenau",
         art.get("status") in ("korrekt", "vertretbar") and r["bewertung"] != "falsch", f"{r['bewertung']} · {_el(r)}")


# ---------------------------------------------------------------- Auftrag 5
#
# Aufgabe «Unfall in der Bäckerei» aus dem Feedback vom 20.10.2026. Sachverhalt und erwartete
# Elemente sind rekonstruiert (siehe _quelle in der Datei), bis die Aufgabe aus der its.db vorliegt.

BAECKEREI = json.loads((ROOT / "tests" / "daten" / "baeckerei.json").read_text(encoding="utf-8"))
LAEUFE = 5


def _mit_strenge(lesson: dict, strenge: str) -> dict:
    return dict(lesson, einstellungen=dict(lesson.get("einstellungen") or {}, bewertungsstrenge=strenge))


@paket("D-19")
def eval_d19(b: Bericht, anzahl: int):
    """Begründungstiefe: Die Bäckerei-Antwort auf der Ebene der Frage gilt als korrekt."""
    from app import tutor
    task, antwort = BAECKEREI["aufgabe"], BAECKEREI["antworten"]["d19"]
    lesson = _mit_strenge(lektion(HAFTUNG), "ausgewogen")
    b.abschnitt("D-19 Begründungstiefe", f"Antwort «{antwort}», Bewertungsstrenge ausgewogen, {LAEUFE} Läufe.")
    urteile = []
    for i in range(LAEUFE):
        r = tutor.evaluate_answer(lesson, tutor.new_profile(), task, antwort)
        urteile.append(r["bewertung"])
        b.text(f"- Lauf {i + 1}: **{r['bewertung']}** · {_el(r)}\n  Feedback: {zitat(r.get('feedback'), 300)[2:]}")
    b.ak("D-19", "AK 1 Bäckerei-Antwort korrekt in mindestens 4 von 5 Läufen", urteile.count("korrekt") >= 4,
         " ".join(urteile))
    falsch = tutor.evaluate_answer(lesson, tutor.new_profile(), task, "Die Kundin. Tierhalterhaftung.")
    b.ak("D-19", "AK 5 eine falsche Antwort bleibt falsch", falsch["bewertung"] == "falsch",
         f"{falsch['bewertung']} · {_el(falsch)}")


@paket("D-20")
def eval_d20(b: Bericht, anzahl: int):
    """Sinngleiche Formulierungen: drei Varianten des Fachbegriffs bei allen drei Bewertungsstrengen."""
    from app import tutor
    task = BAECKEREI["aufgabe"]
    b.abschnitt("D-20 Sinngleiche Formulierungen", f"Drei Varianten, drei Bewertungsstrengen, je {LAEUFE} Läufe.")
    zeilen = ["| Strenge | Antwort | Urteile | erfüllt |", "|---|---|---|---|"]
    alle_ok = True
    for strenge in ("nachsichtig", "ausgewogen", "streng"):
        lesson = _mit_strenge(lektion(HAFTUNG), strenge)
        for antwort in BAECKEREI["antworten"]["d20"]:
            urteile = [tutor.evaluate_answer(lesson, tutor.new_profile(), task, antwort)["bewertung"]
                       for _ in range(LAEUFE)]
            ok = urteile.count("korrekt") >= 4
            alle_ok &= ok
            zeilen.append(f"| {strenge} | {antwort} | {' '.join(urteile)} | {'ja' if ok else 'nein'} |")
    b.text("\n".join(zeilen))
    b.ak("D-20", "AK 1/AK 2 jede Variante bei jeder Strenge korrekt in mindestens 4 von 5 Läufen", alle_ok)
    lesson = _mit_strenge(lektion(HAFTUNG), "ausgewogen")
    r = tutor.evaluate_answer(lesson, tutor.new_profile(), task, BAECKEREI["antworten"]["ohne_fachbegriff"])
    art = r["elemente"][1]["status"] if len(r.get("elemente") or []) > 1 else "?"
    b.ak("D-20", "AK 3 ohne Fachbegriff bleibt die Art der Haftung ungenau oder fehlend",
         art in ("ungenau", "fehlt"), f"{r['bewertung']} · {_el(r)}")


def vergleich_mit_vorlauf(b: Bericht, name: str = "eval_2026-10-12_1613.md") -> None:
    """Abschluss Auftrag 3: Vergleich mit dem letzten Bericht aus Auftrag 2, sofern er vorliegt."""
    pfad = ROOT / "tests" / "eval" / "berichte" / name
    if not pfad.exists():
        b.abschnitt(f"Vergleich mit {name}", "Der Bericht liegt in diesem Ordner nicht vor (er entstand auf a9-mega).")
        return
    zeilen = [z for z in pfad.read_text(encoding="utf-8").splitlines() if z.startswith("| D-") or z.startswith("| T-")]
    b.abschnitt(f"Vergleich mit {name}", "Kriterien des Vorlaufs (Auftrag 2) zum Vergleich:\n\n"
                "| Paket | Kriterium | Ergebnis | Detail |\n|---|---|---|---|\n" + "\n".join(zeilen))


# ---------------------------------------------------------------- Ablauf

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pakete", nargs="*", help="z.B. D-01 D-05 (Standard: alle)")
    ap.add_argument("--anzahl", type=int, default=10, help="Aufgaben pro Lektion und Niveau (Standard 10)")
    ap.add_argument("--mock", action="store_true", help="Rauchtest mit Mock-Provider")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--haftung", help="ID der Haftungsrecht-Lektion, z.B. die Version 3 (Auftrag 2)")
    args = ap.parse_args()
    if args.haftung:
        global HAFTUNG
        HAFTUNG = args.haftung
    if args.mock:
        os.environ["LLM_PROVIDER"] = "mock"
    random.seed(args.seed)
    import logging
    logging.disable(logging.INFO)        # nur Warnungen und Fehler auf der Konsole
    from app import llm
    if llm.provider_name() == "mock" and not args.mock:
        print("Achtung: LLM_PROVIDER=mock. Für eine echte Evaluation das Modell in der .env "
              "eintragen oder mit --mock bewusst einen Rauchtest starten.")
        sys.exit(2)
    wahl = [p.upper() for p in args.pakete] or list(PAKETE)
    b = Bericht(llm.provider_name(), llm.current_model())
    t0 = time.time()
    for name in wahl:
        if name not in PAKETE:
            print(f"Unbekanntes Paket: {name}. Verfügbar: {', '.join(PAKETE)}")
            sys.exit(2)
        print(f"{name}: {PAKETE[name].__doc__.strip().splitlines()[0]}")
        PAKETE[name](b, args.anzahl)
    if any(n in wahl for n in ("D-13", "D-14", "D-15", "D-16", "D-17", "D-18")):
        vergleich_mit_vorlauf(b)
    b.text(f"\n---\nLaufzeit: {round((time.time() - t0) / 60, 1)} Minuten.")
    pfad = b.schreiben()
    ok = all(e[2] for e in b.ergebnisse)
    print(f"\nBericht: {pfad}\n{sum(e[2] for e in b.ergebnisse)} von {len(b.ergebnisse)} Kriterien erfüllt.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
