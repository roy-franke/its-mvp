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
