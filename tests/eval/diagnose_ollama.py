"""Diagnose leerer Modellantworten und Kalibrierung der Tokenschätzung (T-08, T-09).

Läuft gegen das echte Ollama aus der .env (z.B. qwen3:30b auf a9-mega), nicht
in der normalen Testsuite. Das Skript erzeugt mit der Tutorlogik die echten
Prompts einer Lektion (Aufgabe, Theorie, Bewertung) und schickt jeden Prompt
in mehreren Varianten an Ollama:

  A  format=json, think=false        (Standard bis September 2026)
  B  ohne format, think=false        (zweiter Versuch seit T-09)
  C  format=json, think=false, Prompt mit «/no_think»
  D  format=json, ohne think-Feld    (Modell entscheidet selbst)

Pro Aufruf werden done_reason, prompt_eval_count, eval_count, Dauer, Länge
von content und thinking sowie die Lesbarkeit als JSON festgehalten. Am Ende
steht eine Tabelle pro Variante und der Vergleich der Tokenschätzung mit
prompt_eval_count (Kalibrierung für T-08).

    python tests/eval/diagnose_ollama.py                        # Quantenphysik, 3 Durchläufe
    python tests/eval/diagnose_ollama.py --lektion haftungsrecht --anzahl 5

Der Bericht landet unter tests/eval/berichte/diagnose_ollama_<datum>.md.
"""

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from app import llm, tutor  # noqa: E402

VARIANTEN = {
    "A": {"format": True, "think": False, "no_think": False},
    "B": {"format": False, "think": False, "no_think": False},
    "C": {"format": True, "think": False, "no_think": True},
    "D": {"format": True, "think": None, "no_think": False},
}


def prompts_der_lektion(lesson: dict) -> list[tuple[str, str, str]]:
    """Sammelt (Schrittart, System, User) aus den echten Tutor-Funktionen."""
    gesammelt: list[tuple[str, str, str]] = []

    def fang(system, user, json_mode=False):
        gesammelt.append((llm._label(user), system, user))
        return "{}", {}
    original = llm._PROVIDERS["mock"]
    llm._PROVIDERS["mock"] = fang
    os.environ["LLM_PROVIDER_ORIGINAL"] = os.getenv("LLM_PROVIDER", "")
    os.environ["LLM_PROVIDER"] = "mock"
    try:
        p = tutor.new_profile()
        tutor.generate_assessment(lesson)
        tutor.generate_theory(lesson, p, [])
        tutor.generate_task(lesson, p, [])
        tutor.evaluate_answer(lesson, p, {"frage": "Erkläre in eigenen Worten.", "inhalt": "",
                                          "erwartete_antwort": "Eine kurze Musterlösung."},
                              "Ich weiss es nicht genau, aber es hat mit Messungen zu tun.")
    finally:
        llm._PROVIDERS["mock"] = original
        os.environ["LLM_PROVIDER"] = os.environ.pop("LLM_PROVIDER_ORIGINAL")
    eindeutig = {}
    for label, s, u in gesammelt:
        eindeutig.setdefault(label, (label, s, u))
    return list(eindeutig.values())


def aufruf(system: str, user: str, variante: dict) -> dict:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = llm.ollama_payload(system, user + ("\n/no_think" if variante["no_think"] else ""),
                                 json_mode=variante["format"])
    if variante["think"] is None:
        payload.pop("think", None)
    else:
        payload["think"] = variante["think"]
    t0 = time.perf_counter()
    r = httpx.post(f"{base}/api/chat", json=payload, timeout=llm.TIMEOUT)
    dauer = time.perf_counter() - t0
    r.raise_for_status()
    d = r.json()
    inhalt = (d.get("message") or {}).get("content") or ""
    denken = (d.get("message") or {}).get("thinking") or ""
    return {
        "done_reason": d.get("done_reason"), "prompt_eval_count": d.get("prompt_eval_count"),
        "eval_count": d.get("eval_count"), "sekunden": round(dauer, 1),
        "content_zeichen": len(inhalt.strip()), "thinking_zeichen": len(denken),
        "think_tag": "<think>" in inhalt.lower(),
        "json_ok": isinstance(llm.extract_json(llm.strip_reasoning(inhalt)), dict),
        "geschaetzt": llm.prompt_tokens_schaetzen(system, user),
        "anfang": inhalt.strip()[:80],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lektion", default="einfuhrung-in-die-quantenphysik")
    ap.add_argument("--anzahl", type=int, default=3)
    ap.add_argument("--varianten", default="ABCD")
    args = ap.parse_args()
    lesson_dir = Path(os.getenv("ITS_LESSONS_DIR") or ROOT / "app" / "lessons")
    lesson = json.loads((lesson_dir / f"{args.lektion}.json").read_text(encoding="utf-8"))
    prompts = prompts_der_lektion(lesson)
    zeilen, ergebnisse = [], []
    for v in args.varianten:
        for label, system, user in prompts:
            for i in range(args.anzahl):
                try:
                    e = aufruf(system, user, VARIANTEN[v])
                except Exception as ex:   # Verbindung, Zeitüberschreitung
                    e = {"fehler": f"{type(ex).__name__}: {ex}"}
                e.update(variante=v, schritt=label, lauf=i + 1)
                ergebnisse.append(e)
                print(json.dumps(e, ensure_ascii=False))
    zeilen.append(f"# Diagnose Ollama ({os.getenv('OLLAMA_MODEL')}, Lektion {args.lektion})\n")
    zeilen.append(f"Datum: {datetime.datetime.now():%d.%m.%Y %H:%M}, OLLAMA_NUM_CTX={llm.num_ctx()}, "
                  f"OLLAMA_NUM_PREDICT={os.getenv('OLLAMA_NUM_PREDICT', '1024')}\n")
    zeilen.append("| Variante | Aufrufe | leer | JSON ok | done_reason=length | <think> in content | thinking gefüllt |")
    zeilen.append("|---|---|---|---|---|---|---|")
    for v in args.varianten:
        es = [e for e in ergebnisse if e["variante"] == v and "fehler" not in e]
        zeilen.append(f"| {v} | {len(es)} | {sum(e['content_zeichen'] == 0 for e in es)} | "
                      f"{sum(e['json_ok'] for e in es)} | {sum(e['done_reason'] == 'length' for e in es)} | "
                      f"{sum(e['think_tag'] for e in es)} | {sum(e['thinking_zeichen'] > 0 for e in es)} |")
    zeilen.append("\n## Kalibrierung der Tokenschätzung (T-08)\n")
    zeilen.append("| Schritt | geschätzt | prompt_eval_count (max) | Verhältnis |")
    zeilen.append("|---|---|---|---|")
    for label, _, _ in prompts:
        es = [e for e in ergebnisse if e["schritt"] == label and e.get("prompt_eval_count")]
        if es:
            g, m = es[0]["geschaetzt"], max(e["prompt_eval_count"] for e in es)
            zeilen.append(f"| {label} | {g} | {m} | {g / m:.2f} |")
    zeilen.append("\nVerhältnis über 1 heisst: Die Schätzung ist vorsichtig (überschätzt). Wegen des "
                  "Prompt-Caches kann prompt_eval_count bei Folgeaufrufen kleiner sein; massgebend ist "
                  "der grösste Wert.\n")
    ziel = ROOT / "tests" / "eval" / "berichte"
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"diagnose_ollama_{datetime.datetime.now():%Y%m%d_%H%M}.md"
    datei.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"\nBericht: {datei}")


if __name__ == "__main__":
    main()
