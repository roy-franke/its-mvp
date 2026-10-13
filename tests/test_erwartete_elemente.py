"""D-10: Frage nennt alles, was die Antwort enthalten soll."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())


def test_ak1_jede_neue_aufgabe_hat_gespeicherte_elemente():
    t = tutor.generate_task(LESSON, dict(tutor.new_profile(), level="advanced"), [])
    # D-14: Dimension und erwarteter Inhalt
    assert [e["dimension"] for e in t["erwartete_elemente"]] == [
        "Entscheid, ob Anna zahlen muss", "Begründung mit den Voraussetzungen der Verschuldenshaftung"]
    assert all(e["erwartet"] for e in t["erwartete_elemente"])
    assert "erwartete_elemente" not in tutor.fuer_lernende(t)      # intern, wie die Musterlösung


def test_ak1_ohne_elemente_vom_modell_gilt_die_musterloesung(monkeypatch):
    aufgabe = json.loads(llm._mock_text("", "AUFGABE: NAECHSTE_AUFGABE\n"))
    aufgabe.pop("erwartete_elemente")
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (json.dumps(aufgabe), {}))
    t = tutor.generate_task(LESSON, dict(tutor.new_profile(), level="advanced"), [])
    assert t["erwartete_elemente"] == [{"dimension": "Kern der Antwort", "erwartet": aufgabe["erwartete_antwort"]}]
    assert any("erwartete_elemente" in v for v in t["_verstoesse"])


@pytest.mark.parametrize("frage", [
    "Welche der vier Voraussetzungen für eine Haftung ist hier am stärksten erkennbar?",
    "Wer ist für den beschädigten Wagen verantwortlich?",
])
def test_ak2_einteilige_frage_mit_zwei_elementen_ist_verstoss(frage):
    task = {"frage": frage, "erwartete_elemente": ["verantwortliche Person", "Art der Haftung"]}
    assert "genau eine Sache" in didaktik.elemente_passen_zur_frage(task)
    assert didaktik.elemente_passen_zur_frage(dict(task, erwartete_elemente=["Person"])) is None


@pytest.mark.parametrize("frage", [
    "Nenne die verantwortliche Person und die Art der Haftung.",
    "Wer haftet, und warum?",
    "Welche Voraussetzungen sind erfüllt?",
    "Wer ist verantwortlich? Begründe mit dem Gesetz.",
])
def test_mehrteilige_fragen_sind_kein_verstoss(frage):
    assert didaktik.elemente_passen_zur_frage({"frage": frage, "erwartete_elemente": ["a", "b"]}) is None


def test_ak3_bewertung_verwendet_die_gespeicherten_elemente(monkeypatch):
    prompts = []
    original = llm._PROVIDERS["mock"]

    def spy(system, user, json_mode=False):
        prompts.append(user)
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    task = {"frage": "Muss Anna zahlen? Begründe.", "erwartete_antwort": "Ja, weil …",
            "erwartete_elemente": ["Entscheid", "Begründung"]}
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), task, "x" * 60)
    assert "festgelegt (2)" in prompts[-1] and "1) Entscheid" in prompts[-1] and "2) Begründung" in prompts[-1]
    assert "Bestimme 2-4 zentrale Elemente" not in prompts[-1]
    assert [e["element"] for e in r["elemente"]] == ["Entscheid", "Begründung"]
    assert r["elemente_quelle"] == "aufgabe"


def test_ak3_falsche_anzahl_elemente_fuehrt_zur_korrektur(monkeypatch):
    antworten = iter([
        {"elemente": [{"element": "a", "status": "korrekt"}], "bewertung": "korrekt", "feedback": "Gut.",
         "hinweis": ""},
        {"elemente": [{"element": "a", "status": "korrekt"}, {"element": "b", "status": "fehlt"}],
         "bewertung": "teilweise", "feedback": "Es fehlt die Begründung.", "hinweis": "Warum?"}])
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (json.dumps(next(antworten)), {}))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(),
                              {"frage": "?", "erwartete_elemente": ["Entscheid", "Begründung"]}, "Ja")
    assert r["bewertung"] == "teilweise" and r["_versuche"] == 2


def test_alte_aufgaben_ohne_elemente_behalten_den_bisherigen_weg(monkeypatch):
    prompts = []
    original = llm._PROVIDERS["mock"]
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: prompts.append(u) or original(s, u))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), {"frage": "Wer haftet?"}, "x" * 60)
    assert "Bestimme 2-4 zentrale Elemente" in prompts[-1]


def test_lehrperson_sieht_die_erwarteten_elemente():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Elemente"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        t = c.post(f"/api/session/{sid}/next").json()["task"]
        if t["typ"] == "aufgabe":
            break
    assert "erwartete_elemente" not in t
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    aufgabe = [e["payload"] for e in events if e["type"] == "task" and e["payload"].get("typ") == "aufgabe"][-1]
    assert len(aufgabe["erwartete_elemente"]) == 2
