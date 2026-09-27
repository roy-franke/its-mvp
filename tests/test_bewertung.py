"""D-05: Bewertung in zwei Schritten, Strenge und Nachbesserung."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor

from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
HUND = {"typ": "aufgabe", "inhalt": "Der Hund von Frau Meier beisst einen Passanten.",
        "frage": "Welche Haftung greift hier?", "erwartete_antwort": "Tierhalterhaftung nach Art. 56 OR",
        "schluesselbegriffe": ["Tierhalterhaftung"], "konzept": "Tierhalterhaftung"}


@pytest.mark.parametrize("status,widerspruch,urteil", [
    (["korrekt", "korrekt"], False, "korrekt"),
    (["korrekt", "fehlt"], False, "teilweise"),
    (["korrekt", "falsch"], False, "falsch"),
    (["fehlt", "fehlt"], False, "falsch"),
    (["ungenau", "fehlt"], False, "teilweise"),
    (["ungenau", "korrekt"], False, "teilweise"),
    (["ungenau", "falsch"], False, "falsch"),
    (["korrekt", "korrekt"], True, "falsch"),
    ([], False, None),
])
def test_urteil_aus_elementen(status, widerspruch, urteil):
    elemente = [{"element": f"E{i}", "status": s} for i, s in enumerate(status)]
    assert didaktik.urteil_aus_elementen(elemente, widerspruch) == urteil


def _modell(antwort: dict, prompts: list):
    def p(system, user, json_mode=False):
        prompts.append((system, user))
        return json.dumps(antwort), {}
    return p


def test_screenshot4_oberbegriff_ist_teilweise(monkeypatch):
    """Das Modell sagt «korrekt», die Elemente zeigen aber eine Lücke."""
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell({
        "elemente": [{"element": "Haftung ohne Verschulden (Kausalhaftung)", "status": "korrekt"},
                     {"element": "spezifische Form: Tierhalterhaftung", "status": "fehlt"}],
        "sachlicher_widerspruch": False, "bewertung": "korrekt",
        "feedback": "Kausalhaftung stimmt als Oberbegriff.", "hinweis": ""}, prompts))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), HUND, "Kausalhaftung")
    assert r["bewertung"] == "teilweise" and r["bewertung_modell"] == "korrekt"
    assert not r["korrekt"] and len(r["elemente"]) == 2
    user = prompts[0][1]
    assert "Musterlösung (nur für dich, nie verraten): Tierhalterhaftung" in user
    assert "zwei Schritten" in user


def test_sachlicher_widerspruch_nie_richtig(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell({
        "elemente": [{"element": "Haftung der Halterin", "status": "korrekt"}],
        "sachlicher_widerspruch": True, "bewertung": "korrekt", "feedback": "x", "hinweis": ""}, []))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), HUND, "Die Halterin haftet nur bei Absicht.")
    assert r["bewertung"] == "falsch"


def test_ohne_elemente_gilt_das_modellurteil(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(
        {"bewertung": "teilweise", "feedback": "x", "hinweis": "y"}, []))
    assert tutor.evaluate_answer(LESSON, tutor.new_profile(), HUND, "a")["bewertung"] == "teilweise"


@pytest.mark.parametrize("strenge,merkmal", [
    ("nachsichtig", "Eigene Worte statt Fachbegriffe gelten als korrekt"),
    ("ausgewogen", "nur einen Oberbegriff"),
    ("streng", "korrekten Fachbegriffe"),
])
def test_strenge_im_systemprompt(strenge, merkmal):
    lesson = dict(LESSON, einstellungen={"bewertungsstrenge": strenge})
    system = tutor._system_prompt(lesson)
    assert merkmal in system and "Sachliche Fehler gelten" in system


def test_standardstrenge_ausgewogen():
    assert "BEWERTUNGSSTRENGE: ausgewogen" in tutor._system_prompt(LESSON)


def test_nachbesserung_wird_mit_erstem_versuch_bewertet(monkeypatch):
    prompts = []

    def spy(system, user, json_mode=False):
        prompts.append(user)
        return llm._mock_text(system, user), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": "Nachbesserung"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    a1 = c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist."}).json()
    assert a1["bewertung"] == "teilweise" and a1["adaption"] == "retry"
    a2 = c.post(f"/api/session/{sid}/answer",
                json={"answer": "Dazu kommen Widerrechtlichkeit, Kausalzusammenhang und Verschulden."}).json()
    bewerten = [p for p in prompts if "ANTWORT_BEWERTEN" in p]
    assert "Versuch 1 des Lernenden: Anna haftet, weil Schaden da ist." in bewerten[1]
    assert "GESAMTANTWORT" in bewerten[1]
    assert a2["bewertung"] == "korrekt"
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    ev = [e["payload"] for e in events if e["type"] == "answer_evaluated"]
    assert ev[0]["elemente"] and ev[0]["elemente"][1]["status"] == "fehlt"     # AK 3
    assert ev[1]["versuch"] == 2
    # Neue Aufgabe beginnt ohne frühere Versuche
    c.post(f"/api/session/{sid}/next")
    c.post(f"/api/session/{sid}/answer", json={"answer": "x" * 50})
    assert "Versuch 1 des Lernenden" not in [p for p in prompts if "ANTWORT_BEWERTEN" in p][-1]


def test_zweite_unvollstaendige_nachbesserung_wird_akzeptiert():
    """README: bleibt die Nachbesserung unvollständig, geht es weiter."""
    p = tutor.new_profile()
    tutor.adapt(p, "teilweise")
    action, reason = tutor.adapt(p, "teilweise")
    assert action == "next" and "Ergänzungen" in reason


def test_bewertung_mit_temperatur_null(monkeypatch):
    """D-05 nach dem vollen Lauf: Die Bewertung läuft reproduzierbar mit Temperatur 0,
    die Aufgabengenerierung mit der Standardtemperatur des Modells."""
    gesehen = []

    def p(system, user, json_mode=False):
        gesehen.append((user.split("\n")[0], llm.temperatur(), llm.ollama_payload(system, user)["options"]))
        return json.dumps({"elemente": [{"element": "E", "status": "ungenau"}], "bewertung": "teilweise",
                           "feedback": "Du nennst den Oberbegriff.", "hinweis": "Welche Haftung genau?"}), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), HUND, "Kausalhaftung")
    assert r["bewertung"] == "teilweise"
    assert gesehen[0][1] == 0 and gesehen[0][2]["temperature"] == 0
    assert llm.temperatur() is None          # nach dem Aufruf zurückgesetzt
    assert "temperature" not in llm.ollama_payload("s", "u")["options"]


def test_prompt_kennt_ungenau_und_widerspruch(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell({
        "elemente": [{"element": "E", "status": "korrekt"}], "bewertung": "korrekt",
        "feedback": "Stimmt.", "hinweis": ""}, prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), HUND, "Tierhalterhaftung")
    user = prompts[0][1]
    assert "ungenau" in user and "anderen Ergebnis als die Musterlösung" in user
    assert "nur was die Frage tatsächlich verlangt" in user
