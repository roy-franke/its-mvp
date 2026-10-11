"""D-11: Kopierte Antworten erkennen (Entscheid E3)."""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, store, tutor
from app.main import app

# Tutor-Text und Antwort aus dem Screenshot des Feedbacks (Punkt 8)
TUTOR_TEXT = ("Wenn du die Position sehr präzise bestimmst, wird die Geschwindigkeitsmessung ungenauer. Dies "
              "liegt nicht an der Messmethode, sondern daran, dass Teilchen in Wahrscheinlichkeitsverteilungen "
              "existieren. Je genauer du den Ort misst, desto mehr wird die Geschwindigkeit unscharf, weil die "
              "Messung selbst die Teilchen beeinflusst.")
EIGENE = ("Wenn ich den Ort eines Elektrons genau festlege, kann ich seinen Impuls nur noch grob angeben. "
          "Die Unschärferelation ist also eine Grenze der Natur und nicht ein Problem meiner Messgeräte.")


def test_ak1_beispiel_aus_dem_screenshot_ist_kopie():
    k = didaktik.kopie_pruefen(TUTOR_TEXT, [("Antwort des Tutors im Chat", TUTOR_TEXT), ("Lektionsmaterial", "x")])
    assert k["anteil"] == 1.0 and k["quelle"] == "Antwort des Tutors im Chat"


def test_ak2_eigene_formulierung_mit_fachbegriffen_ist_keine_kopie():
    k = didaktik.kopie_pruefen(EIGENE, [("Antwort des Tutors im Chat", TUTOR_TEXT)])
    assert k["anteil"] < didaktik.TEILKOPIE_SCHWELLE


def test_kurze_antworten_und_fachbegriffe_loesen_nichts_aus():
    assert didaktik.kopie_pruefen("Wahrscheinlichkeitsverteilungen existieren", [("t", TUTOR_TEXT)])["anteil"] == 0


def test_ak3_aus_dem_lektionsmaterial_kopierte_passage():
    lesson = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
    passage = " ".join(lesson["material"].split()[40:75])
    k = didaktik.kopie_pruefen(passage, tutor.kopie_quellen(lesson, []))
    assert k["anteil"] >= didaktik.KOPIE_SCHWELLE and k["quelle"] == "Lektionsmaterial"


def _bis_aufgabe(c, name):
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(4):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            return sid
    raise AssertionError


def test_ak1_ak4_kopie_wird_nicht_bewertet_und_ist_sichtbar(monkeypatch):
    c = TestClient(app)
    sid = _bis_aufgabe(c, "Kopie-1")
    store.log_event(sid, "chat_reply", {"antwort": TUTOR_TEXT})
    aufrufe = []
    original = llm._PROVIDERS["mock"]
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: aufrufe.append(u) or original(s, u))
    a = c.post(f"/api/session/{sid}/answer", json={"answer": TUTOR_TEXT, "confidence": 8}).json()
    assert a["bewertung"] == "kopie" and "eigenen Worten" in a["feedback"]
    assert not [u for u in aufrufe if "ANTWORT_BEWERTEN" in u]          # nicht ans Modell
    assert a["progress"]["wrong"] == 0 and a["progress"]["partial"] == 0
    assert c.get(f"/api/session/{sid}/state").json()["wartet_auf"] == "antwort"
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    kopie = [e["payload"] for e in events if e["type"] == "kopie_erkannt"]
    assert kopie and kopie[0]["anteil"] == 1.0 and kopie[0]["quelle"] == "Antwort des Tutors im Chat"
    # Die nächste, eigene Antwort übernimmt die Sicherheitsangabe von vorher
    b = c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil sie das Board fahrlässig "
                                                             "beschädigt hat und alles zutrifft."}).json()
    assert b["bewertung"] == "korrekt"
    sub = [e["payload"] for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"]
           if e["type"] == "answer_submitted"]
    assert sub[-1]["confidence"] == 8


def test_teilkopie_geht_als_hinweis_an_die_bewertung(monkeypatch):
    prompts = []
    original = llm._PROVIDERS["mock"]
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: prompts.append(u) or original(s, u))
    lesson = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
    r = tutor.evaluate_answer(lesson, tutor.new_profile(), {"frage": "?"}, "x" * 50,
                              uebernommen=["die messung selbst die teilchen beeinflusst"])
    assert "Wörtlich aus angezeigten Texten übernommen" in prompts[-1] and r["bewertung"]
