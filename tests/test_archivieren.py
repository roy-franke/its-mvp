"""T-20: Archivieren in der Oberfläche."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def _sequenz(name, lesson="haftungsrecht"):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": name})
    r = c.post("/api/session/start", json={"lesson_id": lesson, "neu_beginnen": True}).json()
    return c, r["session_id"]


def _status(sid):
    return TestClient(app).get(f"/api/teacher/sessions/{sid}").json()["session"]["status"]


def test_ak1_einzeln_und_mehrere_archivieren_und_wiederherstellen():
    _, a = _sequenz("Archiv-A")
    _, b = _sequenz("Archiv-B")
    c = TestClient(app)
    r = c.post("/api/teacher/sessions/archivieren", json={"ids": [a, b]}).json()
    assert r["anzahl"] == 2 and _status(a) == _status(b) == "archiviert"
    standard = [s["session_id"] for s in c.get("/api/teacher/sessions").json() if s["status"] != "archiviert"]
    assert a not in standard
    w = c.post(f"/api/teacher/sessions/{a}/wiederherstellen").json()
    assert w["status"] == "pausiert" and _status(a) == "pausiert"
    events = c.get(f"/api/teacher/sessions/{a}").json()["events"]
    wechsel = [(e["payload"]["von"], e["payload"]["nach"]) for e in events if e["type"] == "status_geaendert"]
    assert wechsel[-2:] == [("aktiv", "archiviert"), ("archiviert", "pausiert")]


def test_ak3_hoechstens_eine_offene_sequenz_beim_wiederherstellen():
    lernend, alt = _sequenz("Archiv-Regel")
    lernend.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True})   # archiviert alt
    assert _status(alt) == "archiviert"
    c = TestClient(app)
    r = c.post(f"/api/teacher/sessions/{alt}/wiederherstellen")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "offene_sequenz"
    neu = r.json()["detail"]["session_id"]
    r = c.post(f"/api/teacher/sessions/{alt}/wiederherstellen?bestehende_archivieren=true")
    assert r.status_code == 200 and _status(alt) != "archiviert" and _status(neu) == "archiviert"


def test_ak2_lernende_erhalten_403(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    c, sid = _sequenz("Archiv-Lernende")
    assert c.post("/api/teacher/sessions/archivieren", json={"ids": [sid]}).status_code == 403
    assert c.post(f"/api/teacher/sessions/{sid}/wiederherstellen").status_code == 403
    assert TestClient(app).post("/api/teacher/sessions/archivieren", json={"ids": [sid]}).status_code == 401


def test_ak4_lektion_archivieren_und_wiederherstellen():
    c = TestClient(app)
    lid = c.post("/api/teacher/lessons", json={"titel": "Archiv Lektion", "lernziele": ["Ziel"],
                                               "material": "Haftung nach Art. 41 OR. " * 10}).json()["id"]
    c.delete(f"/api/teacher/lessons/{lid}")
    assert lid not in [l["id"] for l in c.get("/api/lessons").json()]
    assert c.post(f"/api/teacher/lessons/{lid}/wiederherstellen").json()["ok"]
    assert lid in [l["id"] for l in c.get("/api/lessons").json()]
    html = Path("static/lessons.html").read_text(encoding="utf-8")
    assert "Löschen" not in html and "gelöscht" not in html and "Wiederherstellen" in html
