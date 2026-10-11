"""T-14: Vollständiger Verlauf nach dem Fortsetzen."""

from fastapi.testclient import TestClient

from app import llm
from app.main import app

GUT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


def _ablauf(name):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    c.post(f"/api/session/{sid}/next?prefetch=true")                # Vorabruf, danach verworfen
    c.post(f"/api/session/{sid}/next")                              # Theorie
    c.post(f"/api/session/{sid}/chat", json={"message": "Was heisst adäquat?"})
    c.post(f"/api/session/{sid}/next")                              # Aufgabe
    c.post(f"/api/session/{sid}/answer", json={"answer": "Schaden ist da.", "confidence": 5})  # teilweise
    c.post(f"/api/session/{sid}/pausieren")
    return c, sid


def test_ak1_alle_eintraege_mit_eigenen_antworten(monkeypatch):
    c, sid = _ablauf("Verlauf-Fortsetzen-1")
    st = c.post(f"/api/session/{sid}/fortsetzen").json()
    arten = [e["art"] for e in st["verlauf"]]
    assert arten[:1] == ["einstufung"]
    for art in ("theorie", "frage", "tutor", "aufgabe", "antwort", "bewertung", "status"):
        assert art in arten, art
    antworten = [e["text"] for e in st["verlauf"] if e["art"] == "antwort"]
    assert antworten == ["Schaden ist da."]


def test_ak2_reihenfolge_entspricht_dem_event_log():
    c, sid = _ablauf("Verlauf-Fortsetzen-2")
    st = c.post(f"/api/session/{sid}/fortsetzen").json()
    zeiten = [e["zeit"] for e in st["verlauf"]]
    assert zeiten == sorted(zeiten)
    arten = [e["art"] for e in st["verlauf"]]
    assert arten.index("theorie") < arten.index("frage") < arten.index("aufgabe") < arten.index("antwort")
    status = [(e["von"], e["nach"]) for e in st["verlauf"] if e["art"] == "status"]
    assert status[-2:] == [("aktiv", "pausiert"), ("pausiert", "aktiv")]   # Trennlinie möglich


def test_ak3_keine_internen_eintraege():
    c, sid = _ablauf("Verlauf-Fortsetzen-3")
    st = c.post(f"/api/session/{sid}/fortsetzen").json()
    text = str(st["verlauf"])
    for intern in ("vorabruf", "regel_verstoss", "erwartete_antwort", "schluesselbegriffe", "elemente",
                   "Mock-Fehler", "fallback_used", "grund"):
        assert intern not in text, intern


def test_ak4_kein_llm_aufruf_beim_fortsetzen(monkeypatch):
    c, sid = _ablauf("Verlauf-Fortsetzen-4")
    aufrufe = []
    original = llm._PROVIDERS["mock"]
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: aufrufe.append(u) or original(s, u))
    st = c.post(f"/api/session/{sid}/fortsetzen").json()
    assert st["wartet_auf"] == "antwort" and aufrufe == []


def test_n05_verlauf_bleibt_unveraendert_schlank():
    c, sid = _ablauf("Verlauf-Fortsetzen-5")
    v = c.get(f"/api/me/sequenzen/{sid}/verlauf").json()
    arten = {e["art"] for e in v["eintraege"]}
    assert not arten & {"status", "notiz", "einstufung"}
