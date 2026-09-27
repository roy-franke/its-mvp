"""Evaluation der didaktischen Pakete gegen ein echtes Sprachmodell.

Läuft NICHT in der normalen Testsuite, sondern von Hand, nachdem ein echtes
Modell in der .env konfiguriert ist (z.B. LLM_PROVIDER=ollama mit qwen3:30b).
Das Skript ruft die Tutorlogik direkt auf (ohne Server), prüft die
Akzeptanzkriterien der Pakete D-01 bis D-06 und schreibt einen lesbaren
Bericht nach tests/eval/berichte/.

    python tests/eval/eval_didaktik.py                  # alle Pakete
    python tests/eval/eval_didaktik.py D-01 D-05        # nur ausgewählte
    python tests/eval/eval_didaktik.py --anzahl 3       # schneller Probelauf
    python tests/eval/eval_didaktik.py --mock           # Rauchtest ohne Modell

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


HAFTUNG = "haftungsrecht"
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
        self.teile.append(f"\n## {titel}\n\n{text}".rstrip() + "\n")

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
    for lid in (HAFTUNG, BRUCH):
        lesson = lektion(lid)
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
                p["last_type"] = "theorie"
                task = tutor.generate_task(lesson, p, history)
                eintrag = {
                    "lektion": lesson["titel"], "niveau": level, "theorie": theorie, "task": task,
                    "loesungswort": didaktik.loesungswort_in_aufgabe(task),
                    "beispiel": didaktik.beispiel_wiederverwendet(task, theorie),
                    "abschreibbar": didaktik.abschreibbar(task, theorie),
                    "neu_generiert": task.get("_versuche", 1) > 1,
                    "fallback": bool(task.get("_fallback")),
                }
                alle.append(eintrag)
                print(f"    {lid[:12]} {level:12} {i + 1}/{anzahl}: "
                      f"{'Verstoss' if eintrag['loesungswort'] or eintrag['beispiel'] else 'ok'}")
    echt = [e for e in alle if not e["fallback"]]
    lw = [e for e in echt if e["loesungswort"]]
    bsp = [e for e in echt if e["beispiel"]]
    ab = [e for e in echt if e["abschreibbar"]]
    neu = [e for e in echt if e["neu_generiert"]]
    b.ak("D-01", "AK 1 keine Aufgabe mit Lösungswort in der Frage", not lw,
         f"{len(lw)} von {len(echt)}")
    b.ak("D-01", "AK 2 kein wiederverwendetes Theorie-Beispiel", not bsp, f"{len(bsp)} von {len(echt)}")
    b.text(f"Aufgaben insgesamt: {len(alle)}, davon Fallbacks: {len(alle) - len(echt)}. "
           f"Nach einem Regelverstoss neu generiert: {len(neu)}. Abschreibbar trotz Prüfung: {len(ab)}. "
           "Multiple-Choice-Aufgaben: "
           f"{sum(1 for e in echt if e['task'].get('aufgabentyp') == 'multiple_choice')}.")
    typen: dict[str, int] = {}
    for e in echt:
        typen[e["task"].get("aufgabentyp", "?")] = typen.get(e["task"].get("aufgabentyp", "?"), 0) + 1
    b.text("Aufgabentypen: " + ", ".join(f"{k} {v}" for k, v in sorted(typen.items())) + ".")
    for titel, liste, feld in (("Verstösse Lösungswort", lw, "loesungswort"),
                               ("Verstösse Beispiel", bsp, "beispiel")):
        if liste:
            b.text(f"\n### {titel}\n")
            for e in liste:
                b.text(f"- {e['lektion']}, {e['niveau']}: «{e['task'].get('frage', '')}» – {e[feld]}")
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
        adaption = a["adaption"] if a["adaption"] in ("simplify", "explain") else ""
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


# ---------------------------------------------------------------- Ablauf

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pakete", nargs="*", help="z.B. D-01 D-05 (Standard: alle)")
    ap.add_argument("--anzahl", type=int, default=10, help="Aufgaben pro Lektion und Niveau (Standard 10)")
    ap.add_argument("--mock", action="store_true", help="Rauchtest mit Mock-Provider")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
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
    b.text(f"\n---\nLaufzeit: {round((time.time() - t0) / 60, 1)} Minuten.")
    pfad = b.schreiben()
    ok = all(e[2] for e in b.ergebnisse)
    print(f"\nBericht: {pfad}\n{sum(e[2] for e in b.ergebnisse)} von {len(b.ergebnisse)} Kriterien erfüllt.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
