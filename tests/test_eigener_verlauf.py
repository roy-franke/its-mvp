"""N-05: Eigener Lernverlauf für Lernende."""

import json

from fastapi.testclient import TestClient

from app import llm
from app.main import app

GUT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


def _bewertung(system, user, json_mode=False):
    if "ANTWORT_BEWERTEN" in user:
        antwort = user.split("Antwort des Lernenden: ")[-1].split("\n")[0]
        ok = len(antwort) > 30
        return json.dumps({"elemente": [{"element": "Kern", "status": "korrekt" if ok else "falsch"}],
                           "bewertung": "korrekt" if ok else "falsch",
                           "feedback": "Gut begründet." if ok else "Das trifft nicht zu.",
                           "hinweis": "" if ok else "Denk an die vier Voraussetzungen."}), {}
    return llm._mock_text(system, user), {}


def _sequenz(c, name, monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _bewertung)
    sid = c.post("/api/session/start", json={"name": name}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(4):
        t = c.post(f"/api/session/{sid}/next").json()["task"]
        if t["typ"] == "aufgabe":
            break
    c.post(f"/api/session/{sid}/answer", json={"answer": "keine Ahnung", "confidence": 9})
    c.post(f"/api/session/{sid}/answer", json={"answer": GUT})
    c.post(f"/api/session/{sid}/chat", json={"message": "Was heisst widerrechtlich?"})
    return sid, t


def test_nur_eigene_verlaeufe(monkeypatch):
    """AK 1: Zwei Benutzer, fremde Verläufe sind nicht abrufbar."""
    a, b = TestClient(app), TestClient(app)
    sid_a, _ = _sequenz(a, "Verlauf Anna", monkeypatch)
    sid_b, _ = _sequenz(b, "Verlauf Ben", monkeypatch)
    a.post(f"/api/session/{sid_a}/pausieren")
    b.post(f"/api/session/{sid_b}/pausieren")
    assert a.get(f"/api/me/sequenzen/{sid_a}/verlauf").status_code == 200
    assert b.get(f"/api/me/sequenzen/{sid_b}/verlauf").status_code == 200
    assert a.get(f"/api/me/sequenzen/{sid_b}/verlauf").status_code == 403
    assert b.get(f"/api/me/sequenzen/{sid_a}/verlauf").status_code == 403
    assert TestClient(app).get(f"/api/me/sequenzen/{sid_a}/verlauf").status_code == 401
    # Auch nach einem Namenswechsel im selben Browser nicht
    a.post("/api/learner/login", json={"name": "Verlauf Ben"})
    assert a.get(f"/api/me/sequenzen/{sid_a}/verlauf").status_code == 403


def test_inhalt_ohne_interne_angaben(monkeypatch):
    c = TestClient(app)
    sid, aufgabe = _sequenz(c, "Verlauf Inhalt", monkeypatch)
    assert c.get(f"/api/me/sequenzen/{sid}/verlauf").status_code == 409      # läuft noch
    liste = c.get("/api/me/sequenzen").json()
    assert not liste[0]["verlauf_sichtbar"]
    c.post(f"/api/session/{sid}/pausieren")
    assert c.get("/api/me/sequenzen").json()[0]["verlauf_sichtbar"]
    v = c.get(f"/api/me/sequenzen/{sid}/verlauf").json()
    arten = [e["art"] for e in v["eintraege"]]
    for art in ("theorie", "aufgabe", "antwort", "bewertung", "frage", "tutor"):
        assert art in arten
    antworten = [e for e in v["eintraege"] if e["art"] == "antwort"]
    assert antworten[0]["text"] == "keine Ahnung" and antworten[0]["sicherheit"] == 9
    bew = [e for e in v["eintraege"] if e["art"] == "bewertung"]
    assert bew[0]["bewertung"] == "falsch" and "Denk an" in bew[0]["hinweis"]
    assert "sehr sicher" in bew[0]["selbsteinschaetzung"]
    text = json.dumps(v, ensure_ascii=False)
    for intern in ("adaption", "erwartete_antwort", "schluesselbegriffe", "elemente", "dauer",
                   "fallback", "regel_verstoss", "bewertung_modell", "suchanfrage"):
        assert intern not in text, intern
    # Schwächenliste mit Sprung zur Aufgabe
    assert v["schwaechen"] and v["schwaechen"][0]["konzept"] == aufgabe["konzept"]
    anker = v["schwaechen"][0]["anker"]
    ziel = [e for e in v["eintraege"] if e.get("id") == anker]
    assert ziel and ziel[0]["art"] == "aufgabe" and ziel[0]["frage"] == aufgabe["frage"]


def test_archivierte_nur_auf_wunsch(monkeypatch):
    c = TestClient(app)
    sid, _ = _sequenz(c, "Verlauf Archiv", monkeypatch)
    neu = c.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True}).json()
    assert [x["session_id"] for x in c.get("/api/me/sequenzen").json()] == [neu["session_id"]]
    alle = c.get("/api/me/sequenzen?archivierte=true").json()
    arch = [x for x in alle if x["session_id"] == sid][0]
    assert arch["status"] == "archiviert" and arch["verlauf_sichtbar"]
    assert c.get(f"/api/me/sequenzen/{sid}/verlauf").status_code == 200
