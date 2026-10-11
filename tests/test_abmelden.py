"""T-22: Abmelden ohne Header-Anmeldung."""

from fastapi.testclient import TestClient

from app.main import app


def test_ak1_lehrperson_mit_passwort(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    c = TestClient(app)
    assert c.post("/api/teacher/login", json={"password": "geheim"}).status_code == 200
    assert c.get("/teacher", follow_redirects=False).status_code == 200
    r = c.get("/logout?ziel=lehrperson", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/teacher/login"
    assert r.headers["cache-control"] == "no-store"
    r = c.get("/teacher", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/teacher/login"


def test_ak1_ursache_ohne_passwort_wirkt_abmelden_jetzt(monkeypatch):
    """Ursache des wirkungslosen Links: Ohne TEACHER_PASSWORD leitete /teacher/login
    sofort auf /teacher zurück. Der Abmelde-Merker verhindert das."""
    monkeypatch.setenv("TEACHER_PASSWORD", "")
    c = TestClient(app)
    assert c.get("/teacher", follow_redirects=False).status_code == 200      # lokal ohne Login offen
    r = c.get("/teacher/logout", follow_redirects=False)
    assert r.headers["location"] == "/teacher/login"
    assert c.get("/teacher/login", follow_redirects=False).status_code == 200   # leere Login-Seite
    assert c.get("/teacher", follow_redirects=False).status_code == 307
    assert c.get("/api/teacher/sessions").status_code == 401
    c.post("/api/teacher/login", json={"password": ""})                     # «Anmelden» ohne Passwort
    assert c.get("/teacher", follow_redirects=False).status_code == 200


def test_ak2_lernende_abmelden_pausiert_und_sperrt():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Abmelde-Person"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True}).json()["session_id"]
    r = c.get("/logout?ziel=lernend", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    me = c.get("/api/me").json()
    assert me["name"] is None and me["angemeldet"] is False
    assert c.get("/api/me/sequenzen").status_code == 401
    lp = TestClient(app)
    assert lp.get(f"/api/teacher/sessions/{sid}").json()["session"]["status"] == "pausiert"
    events = lp.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert events[-1]["payload"]["grund"] == "Beim Abmelden pausiert"


def test_api_logout_verwendet_dieselbe_logik():
    c = TestClient(app)
    c.post("/api/teacher/login", json={"password": ""})
    c.post("/api/learner/login", json={"name": "Beides"})
    assert c.post("/api/learner/logout").json()["ok"]
    assert not c.cookies.get("its_teacher") and not c.cookies.get("its_learner")
    assert c.get("/api/me").json()["name"] is None


def test_abmelden_button_gemeldet():
    c = TestClient(app)
    assert c.get("/api/me").json()["abmelden"] is True
