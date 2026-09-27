"""D-02: Einsatzart Einführung / Vertiefung über die API."""

import json

import pytest
from fastapi.testclient import TestClient

from app import llm
from app.main import LESSONS_DIR, app

lp = TestClient(app)
MATERIAL = ("Quantenphysik. Superposition: Ein Teilchen kann sich in einer Überlagerung "
            "mehrerer Zustände befinden, bis gemessen wird. Unschärferelation: Ort und Impuls "
            "lassen sich nicht gleichzeitig beliebig genau bestimmen. Beispiele folgen im Text.")


@pytest.fixture
def lektion():
    ids = []

    def make(einsatzart):
        r = lp.post("/api/teacher/lessons", json={
            "titel": f"Quanten {einsatzart}", "lernziele": ["Konzepte erklären"],
            "material": MATERIAL, "einstellungen": {"einsatzart": einsatzart}})
        ids.append(r.json()["id"])
        return r.json()["id"]
    yield make
    for i in ids:
        (LESSONS_DIR / f"{i}.json").unlink(missing_ok=True)


def _mock_mit_aufgabe(aufgabe: dict, prompts: list):
    def p(system, user, json_mode=False):
        prompts.append(user)
        if "NAECHSTE_AUFGABE" in user:
            return json.dumps(aufgabe), {}
        if "THEORIE_SCHRITT" in user:
            return json.dumps({"titel": "Superposition", "inhalt": "Ein Teilchen kann in mehreren Zuständen sein.",
                               "beispiel": "Eine Münze im Flug ist weder Kopf noch Zahl, weil noch nicht gemessen wurde.",
                               "konzept": "Superposition"}), {}
        return llm._mock_text(system, user), {}
    return p


UNERKLAERT = {"titel": "Messung", "inhalt": "Eine Forscherin misst den Ort eines Elektrons sehr genau.",
              "frage": "Was folgt daraus für die zweite Grösse?", "aufgabentyp": "vorhersagen",
              "erwartete_antwort": "Der Impuls wird ungenau.", "schluesselbegriffe": ["Impuls"],
              "konzept": "Unschärferelation"}


def test_einstellung_gespeichert_und_standard(lektion):
    lid = lektion("vertiefung")
    assert json.loads((LESSONS_DIR / f"{lid}.json").read_text(encoding="utf-8"))["einstellungen"]["einsatzart"] == "vertiefung"
    assert lp.get("/api/teacher/lessons/haftungsrecht").json()["einstellungen"]["einsatzart"] == "einfuehrung"


def test_einfuehrung_schiebt_theorie_ein(lektion, monkeypatch):
    lid = lektion("einfuehrung")
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _mock_mit_aufgabe(UNERKLAERT, prompts))
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": "Einfuehrung", "lesson_id": lid}).json()["session_id"]
    assert any("Alltagserfahrungen" in p for p in prompts if "EINSTUFUNGSFRAGEN" in p)
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t1 = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t1["typ"] == "theorie" and t1["konzept"] == "Superposition"
    t2 = c.post(f"/api/session/{sid}/next").json()["task"]
    # Die Aufgabe verlangt die noch nicht erklärte Unschärferelation:
    # statt der Aufgabe kommt zuerst ein Theorieschritt zu genau diesem Konzept
    assert t2["typ"] == "theorie"
    assert "Unschärferelation" in [p for p in prompts if "THEORIE_SCHRITT" in p][-1]
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    ein = [e["payload"] for e in events if e["type"] == "theorie_eingeschoben"]
    assert ein and ein[0]["konzept"] == "Unschärferelation"
    assert any("noch nicht erklärt" in p for p in prompts if "KORREKTUR" in p)


def test_vertiefung_falsche_antwort_fuehrt_zu_erklaerung(lektion, monkeypatch):
    lid = lektion("vertiefung")
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _mock_mit_aufgabe(UNERKLAERT, prompts))
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": "Vertiefung", "lesson_id": lid}).json()["session_id"]
    assert not any("Alltagserfahrungen" in p for p in prompts)
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})   # Mock: intermediate
    c.post(f"/api/session/{sid}/next")                                        # Theorie Superposition
    t = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "aufgabe" and t["konzept"] == "Unschärferelation"      # Vertiefung darf das
    a = c.post(f"/api/session/{sid}/answer", json={"answer": "weiss nicht"}).json()
    assert a["adaption"] == "explain"
    assert a["progress"]["level"] == "intermediate"                          # keine Senkung
    t3 = c.post(f"/api/session/{sid}/next?adaptation=explain").json()["task"]
    assert t3["typ"] == "theorie"
    assert "Unschärferelation" in [p for p in prompts if "THEORIE_SCHRITT" in p][-1]
