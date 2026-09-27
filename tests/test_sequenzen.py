"""T-05: Lernsequenzen pro Person – fortsetzen, trennen, archivieren, Migration."""

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

GUT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


def browser():
    return TestClient(app)


def _bis_zur_aufgabe(c, sid):
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        t = c.post(f"/api/session/{sid}/next").json()
        if t["task"]["typ"] == "aufgabe":
            return t
    raise AssertionError("keine Aufgabe")


# ---------------------------------------------------------------- AK 1

def test_fortsetzen_in_anderem_browser():
    a = browser()
    sid = a.post("/api/session/start", json={"name": "Lina Fortsetzen"}).json()["session_id"]
    aufgabe = _bis_zur_aufgabe(a, sid)["task"]
    a.post(f"/api/session/{sid}/answer", json={"answer": GUT})
    stand_a = a.get(f"/api/session/{sid}/state").json()

    b = browser()   # anderer Browser, keine Cookies, keine Session-ID
    assert b.post("/api/learner/login", json={"name": "  lina fortsetzen "}).status_code == 200
    liste = b.get("/api/me/sequenzen").json()
    assert [x["session_id"] for x in liste] == [sid]
    assert liste[0]["fortsetzbar"] and liste[0]["step"] == 1
    st = b.post(f"/api/session/{sid}/fortsetzen").json()
    assert st["current_task"] == stand_a["current_task"]
    assert st["current_task"]["frage"] == aufgabe["frage"]
    assert st["wartet_auf"] == "weiter" and st["letztes_feedback"]["bewertung"] == "korrekt"
    assert st["progress"]["step"] == 1
    # Weiterlernen in Browser B funktioniert
    assert b.post(f"/api/session/{sid}/next").status_code == 200


def test_fortsetzen_mitten_in_der_aufgabe():
    a = browser()
    sid = a.post("/api/session/start", json={"name": "Offene Aufgabe"}).json()["session_id"]
    aufgabe = _bis_zur_aufgabe(a, sid)["task"]
    b = browser()
    b.post("/api/learner/login", json={"name": "Offene Aufgabe"})
    st = b.post(f"/api/session/{sid}/fortsetzen").json()
    assert st["wartet_auf"] == "antwort" and st["current_task"]["frage"] == aufgabe["frage"]


def test_fortsetzen_waehrend_einstufung():
    a = browser()
    d = a.post("/api/session/start", json={"name": "Einstufung offen"}).json()
    st = a.post(f"/api/session/{d['session_id']}/fortsetzen").json()
    assert st["wartet_auf"] == "einstufung" and st["questions"] == d["questions"]


# ---------------------------------------------------------------- AK 2

def test_zwei_namen_im_gleichen_browser():
    c = browser()
    sid_a = c.post("/api/session/start", json={"name": "Person A"}).json()["session_id"]
    c.post("/api/learner/login", json={"name": "Person B"})
    sid_b = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    assert [x["session_id"] for x in c.get("/api/me/sequenzen").json()] == [sid_b]
    # Fremde Sequenz: weder lesen noch weiterlernen
    assert c.get(f"/api/session/{sid_a}/state").status_code == 403
    assert c.post(f"/api/session/{sid_a}/next").status_code == 403
    assert c.post(f"/api/session/{sid_a}/chat", json={"message": "hallo"}).status_code == 403
    c.post("/api/learner/login", json={"name": "person a"})
    assert [x["session_id"] for x in c.get("/api/me/sequenzen").json()] == [sid_a]


def test_ohne_anmeldung_kein_zugriff():
    sid = browser().post("/api/session/start", json={"name": "Privat"}).json()["session_id"]
    fremd = browser()
    assert fremd.get(f"/api/session/{sid}/state").status_code == 401
    assert fremd.get("/api/me/sequenzen").status_code == 401


# ---------------------------------------------------------------- AK 3

def test_neu_beginnen_archiviert_mit_zeitstempel():
    c = browser()
    alt = c.post("/api/session/start", json={"name": "Neustart"}).json()["session_id"]
    r = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"})
    assert r.status_code == 409
    assert r.json()["detail"]["session_id"] == alt
    vorher = time.time()
    neu = c.post("/api/session/start", json={"lesson_id": "haftungsrecht",
                                             "neu_beginnen": True}).json()["session_id"]
    assert neu != alt
    liste = [x["session_id"] for x in c.get("/api/me/sequenzen").json()]
    assert liste == [neu]
    # Die Lehrperson sieht die archivierte Sequenz weiterhin vollständig
    rows = {r["session_id"]: r for r in c.get("/api/teacher/sessions").json()}
    assert rows[alt]["status"] == "archiviert" and rows[alt]["archived_at"] >= vorher
    events = c.get(f"/api/teacher/sessions/{alt}").json()["events"]
    wechsel = [e for e in events if e["type"] == "status_geaendert"]
    assert wechsel[-1]["payload"] == {"von": "aktiv", "nach": "archiviert", "grund": "Neu begonnen"}
    assert any(e["type"] == "assessment_questions" for e in events)
    # Archivierte Sequenz lässt sich nicht fortsetzen
    assert c.post(f"/api/session/{alt}/fortsetzen").status_code == 409


def test_abgeschlossene_sequenz_statuswechsel():
    c = browser()
    d = c.post("/api/session/start", json={"name": "Abschluss"}).json()
    sid = d["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(d["total_steps"] * 3):
        t = c.post(f"/api/session/{sid}/next").json()
        if t.get("done"):
            break
        if t["task"]["typ"] == "aufgabe":
            c.post(f"/api/session/{sid}/answer", json={"answer": GUT})
    liste = c.get("/api/me/sequenzen").json()
    assert liste[0]["status"] == "abgeschlossen" and not liste[0]["fortsetzbar"]


# ---------------------------------------------------------------- PIN (E7)

def test_pin_schuetzt_den_namen():
    c = browser()
    assert c.post("/api/learner/login", json={"name": "Pin-Person", "pin": "4711"}).json()["pin_gesetzt"]
    fremd = browser()
    r = fremd.post("/api/learner/login", json={"name": "pin-person"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pin_noetig"
    r = fremd.post("/api/learner/login", json={"name": "pin-person", "pin": "0000"})
    assert r.json()["detail"]["code"] == "pin_falsch"
    assert fremd.post("/api/learner/login", json={"name": "pin-person", "pin": "4711"}).status_code == 200
    # Die PIN liegt nur gehasht in der Datenbank
    assert "4711" not in store.get_user("pin-person")["pin_hash"]


def test_pin_format():
    r = browser().post("/api/learner/login", json={"name": "Formfehler", "pin": "12a"})
    assert r.status_code == 400


def test_ohne_pin_genuegt_der_name():
    browser().post("/api/learner/login", json={"name": "Ohne Pin"})
    assert browser().post("/api/learner/login", json={"name": "ohne pin"}).status_code == 200


# ---------------------------------------------------------------- AK 4 Migration

ALTES_SCHEMA = """
CREATE TABLE sessions (id TEXT PRIMARY KEY, name TEXT NOT NULL, lesson_id TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'assessment', profile TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
    type TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def test_migration_ohne_datenverlust(tmp_path, monkeypatch):
    db = tmp_path / "alt.db"
    c = sqlite3.connect(db)
    c.executescript(ALTES_SCHEMA)
    alt = [("s1", "CF-Q", "quanten", "assessment", 100.0),
           ("s2", "cf-q ", "quanten", "finished", 200.0),
           ("s3", "Roy", "bruch", "learning", 150.0)]
    for sid, name, lesson, phase, t in alt:
        c.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (sid, name, lesson, phase, json.dumps({"step": 1}), t, t))
        for typ in ("session_started", "task", "answer_evaluated"):
            c.execute("INSERT INTO events (session_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
                      (sid, typ, json.dumps({"x": sid}), t))
    c.commit()
    c.close()
    monkeypatch.setattr(store, "DB_PATH", db)
    store.init_db()
    store.init_db()   # idempotent

    sessions = {s["id"]: s for s in store.list_sessions()}
    assert set(sessions) == {"s1", "s2", "s3"}
    for sid, *_ in alt:
        typen = [e["type"] for e in store.get_events(sid)]
        assert typen[:3] == ["session_started", "task", "answer_evaluated"]
        assert sessions[sid]["profile"] == {"step": 1}
    assert sessions["s1"]["user_key"] == sessions["s2"]["user_key"] == "cf-q"
    assert sessions["s3"]["user_key"] == "roy" and sessions["s3"]["status"] == "aktiv"
    # s2 ist die neuere Sequenz derselben Person und Lektion und bleibt offen
    assert sessions["s2"]["status"] == "abgeschlossen"
    assert sessions["s1"]["status"] == "archiviert" and sessions["s1"]["archived_at"]
    assert store.get_events("s1")[-1]["type"] == "status_geaendert"
    assert store.get_user("cf-q") and store.get_user("roy")
    assert [x["id"] for x in store.sessions_of_user("cf-q")] == ["s2"]
