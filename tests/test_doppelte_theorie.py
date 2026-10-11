"""D-08: Keine doppelte Theorie."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, main, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
FAELLE = json.loads(open("tests/daten/doppelte_theorie.json", encoding="utf-8").read())

THEORIE = {"titel": "Kausalhaftung ohne Verschulden", "konzept": "Kausalhaftung",
           "inhalt": FAELLE["haftung"][0]["inhalt"], "beispiel": FAELLE["haftung"][0]["beispiel"]}
AUFGABE = {"titel": "Der umgestürzte Baum", "inhalt": "Ein Baum fällt bei Sturm auf das Auto der Nachbarin.",
           "frage": "Wer muss für das Auto aufkommen, und warum?", "aufgabentyp": "anwenden", "optionen": [],
           "erwartete_antwort": "Der Grundeigentümer haftet als Werkeigentümer ohne Verschulden.",
           "schluesselbegriffe": ["Gefährdungshaftung"], "konzept": "Kausalhaftung"}


class Provider:
    """Theorie zur Kausalhaftung; die erste Aufgabe (Vorabruf) scheitert, danach eine
    Aufgabe, deren Schlüsselbegriff in der Theorie nicht vorkommt."""

    def __init__(self):
        self.aufgaben = 0

    def __call__(self, system, user, json_mode=False):
        label = llm._label(user)
        if label == "THEORIE_SCHRITT":
            return json.dumps(THEORIE, ensure_ascii=False), {}
        if label == "NAECHSTE_AUFGABE":
            self.aufgaben += 1
            if self.aufgaben <= 3:                       # drei Versuche pro Aufgabe
                raise llm.LLMError("Vorabruf scheitert")
            return json.dumps(AUFGABE, ensure_ascii=False), {}
        return llm._mock_text(system, user), {}


def test_ak1_haftungsrecht_fall_reproduziert_und_behoben(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", Provider())
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Doppelte-Theorie"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t1 = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t1["typ"] == "theorie" and t1["konzept"] == "Kausalhaftung"
    c.post(f"/api/session/{sid}/next?prefetch=true")             # Vorabruf endet im Fallback
    t2 = c.post(f"/api/session/{sid}/next").json()["task"]
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    typen = [e["type"] for e in events]
    assert "vorabruf_verworfen" in typen and "regel_verstoss" in typen
    # Vorher: «Theorie eingeschoben: Konzept Kausalhaftung war noch nicht erklärt»
    assert t2["typ"] == "aufgabe", "zweite Theorie zur Kausalhaftung eingeschoben"
    assert "theorie_eingeschoben" not in typen
    assert sum(1 for e in events if e["type"] == "task" and e["payload"].get("typ") == "theorie") == 1


def test_ak2_spezifischeres_konzept_erklaert_das_oberkonzept():
    assert tutor.konzept_erklaert("Kausalhaftung", ["Kausalhaftung ohne Verschulden"])
    assert didaktik.gleiches_konzept("Kausal-Haftung", "kausalhaftung")
    assert didaktik.gleiches_konzept("Unschärferelation", "Heisenbergsche Unschärferelation")
    assert not didaktik.gleiches_konzept("Haftung", "Tierhalterhaftung")
    assert not didaktik.gleiches_konzept("Verschuldenshaftung", "Kausalhaftung ohne Verschulden")


def test_ak2_keine_theorie_fuer_kausalhaftung_nach_kausalhaftung_ohne_verschulden(monkeypatch):
    aufgabe = dict(AUFGABE, schluesselbegriffe=["Kausalhaftung"])
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        json.dumps(aufgabe, ensure_ascii=False), {}) if "NAECHSTE_AUFGABE" in u else (llm._mock_text(s, u), {}))
    p = dict(tutor.new_profile(), level="intermediate", last_type="aufgabe", aufgaben_seit_theorie=1,
             erklaert=["Kausalhaftung ohne Verschulden"], step=2)
    history = [{"type": "task", "payload": dict(THEORIE, typ="theorie", konzept="Kausalhaftung ohne Verschulden"),
                "created_at": 0, "id": 1}]
    art, schritt = main._generate_step(LESSON, p, history, None)
    assert art == "aufgabe" and not schritt.get("_eingeschoben")


def test_ak3_theorie_dazu_markiert_das_konzept_als_erklaert():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Theorie-dazu"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    c.post(f"/api/session/{sid}/next")
    c.post(f"/api/session/{sid}/next")                                      # Aufgabe
    profil = c.get(f"/api/teacher/sessions/{sid}").json()["session"]["profile"]
    profil["erklaert"] = []                                                  # angenommen: nichts erklärt
    from app import store
    store.update_session(sid, profile=profil)
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Theorie bitte", "art": "theorie"}).json()
    profil = c.get(f"/api/teacher/sessions/{sid}").json()["session"]["profile"]
    assert profil["erklaert"] == ["Verschuldenshaftung"]
    assert r["nochmals_anders"] is True          # Theorie war schon gezeigt worden


@pytest.mark.parametrize("fall", ["haftung", "quanten"])
def test_aehnlichkeit_erkennt_die_beiden_faelle_aus_dem_feedback(fall):
    alt, neu = FAELLE[fall]
    assert tutor.doppelte_theorie(neu, [], didaktik.theorietext(alt))
    assert tutor.doppelte_theorie(neu, [alt["konzept"]], "")         # schon als erklärt bekannt


def test_verschiedene_konzepte_sind_keine_wiederholung():
    alt, neu = FAELLE["verschieden"]
    assert tutor.doppelte_theorie(neu, [alt["konzept"]], didaktik.theorietext(alt)) is None


def test_automatische_theorie_zu_erklaertem_konzept_wird_uebersprungen(monkeypatch):
    """Wiederholt das Modell trotz Korrektur ein erklärtes Konzept, kommt direkt die Aufgabe."""
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        json.dumps(dict(FAELLE["quanten"][1]), ensure_ascii=False), {}) if "THEORIE_SCHRITT" in u
        else (llm._mock_text(s, u), {}))
    p = dict(tutor.new_profile(), level="basic", last_type="aufgabe", erklaert=["Unschärferelation"], step=2)
    history = [{"type": "task", "payload": dict(FAELLE["quanten"][0], typ="theorie"), "created_at": 0, "id": 1}]
    art, schritt = main._generate_step(LESSON, p, history, None)
    assert art == "aufgabe" and "bereits erklärt" in schritt["_theorie_uebersprungen"]["grund"]


def test_vereinfachte_erklaerung_ist_gekennzeichnet():
    p = dict(tutor.new_profile(), covered=["Verschuldenshaftung"])
    history = [{"type": "task", "payload": dict(FAELLE["verschieden"][0], typ="theorie"), "created_at": 0, "id": 1}]
    t = tutor.generate_theory(LESSON, p, history, "simplify")
    assert t["nochmals_anders"] is True
