"""T-06: «Pausieren und später weiterfahren» und «Lektion abbrechen»."""

from fastapi.testclient import TestClient

from app.main import app


def _sequenz(name):
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": name}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        t = c.post(f"/api/session/{sid}/next").json()
        if t["task"]["typ"] == "aufgabe":
            return c, sid, t["task"]
    raise AssertionError


def _status_events(c, sid):
    return [e["payload"] for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"]
            if e["type"] == "status_geaendert"]


def test_pausieren_und_wieder_anmelden_fuehrt_zur_gleichen_stelle():
    c, sid, aufgabe = _sequenz("Pause-Person")
    r = c.post(f"/api/session/{sid}/pausieren")
    assert r.json()["status"] == "pausiert"
    neu = TestClient(app)                      # erneutes Anmelden
    neu.post("/api/learner/login", json={"name": "pause-person"})
    eintrag = neu.get("/api/me/sequenzen").json()[0]
    assert eintrag["status"] == "pausiert" and eintrag["fortsetzbar"]
    st = neu.post(f"/api/session/{sid}/fortsetzen").json()
    assert st["status"] == "aktiv"
    assert st["wartet_auf"] == "antwort" and st["current_task"]["frage"] == aufgabe["frage"]
    assert [e["nach"] for e in _status_events(neu, sid)] == ["pausiert", "aktiv"]


def test_abbrechen_setzt_status_und_sperrt_fortsetzen():
    c, sid, _ = _sequenz("Abbruch-Person")
    assert c.post(f"/api/session/{sid}/abbrechen").json()["status"] == "abgebrochen"
    rows = {r["session_id"]: r for r in c.get("/api/teacher/sessions").json()}
    assert rows[sid]["status"] == "abgebrochen" and rows[sid]["status_at"]
    assert c.post(f"/api/session/{sid}/fortsetzen").status_code == 409
    assert c.post(f"/api/session/{sid}/next").status_code == 409
    assert c.post(f"/api/session/{sid}/answer", json={"answer": "x"}).status_code == 409
    # Neu beginnen bleibt möglich
    assert c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).status_code == 409
    assert c.post("/api/session/start", json={"lesson_id": "haftungsrecht",
                                              "neu_beginnen": True}).status_code == 200
    assert _status_events(c, sid)[0] == {"von": "aktiv", "nach": "abgebrochen",
                                         "grund": "Von der lernenden Person abgebrochen"}


def test_beide_aktionen_erzeugen_events():
    c, sid, _ = _sequenz("Event-Person")
    c.post(f"/api/session/{sid}/pausieren")
    c.post(f"/api/session/{sid}/abbrechen")
    assert [e["nach"] for e in _status_events(c, sid)] == ["pausiert", "abgebrochen"]


def test_fremde_duerfen_nicht_pausieren():
    c, sid, _ = _sequenz("Besitzerin")
    fremd = TestClient(app)
    fremd.post("/api/learner/login", json={"name": "Jemand"})
    assert fremd.post(f"/api/session/{sid}/pausieren").status_code == 403
    assert fremd.post(f"/api/session/{sid}/abbrechen").status_code == 403


def test_pausierte_sequenz_wird_beim_weiterlernen_aktiv():
    c, sid, _ = _sequenz("Direkt weiter")
    c.post(f"/api/session/{sid}/pausieren")
    assert c.post(f"/api/session/{sid}/chat", json={"message": "Frage"}).status_code == 200
    assert c.get(f"/api/session/{sid}/state").json()["status"] == "aktiv"
