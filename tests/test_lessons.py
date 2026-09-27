"""Tests für das Lehrpersonen-Modul (Lektionen erstellen)."""

import io
import json
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ.setdefault("ITS_DB_PATH", "/tmp/its_test.db")

from fastapi.testclient import TestClient

from app.main import LESSONS_DIR, app

client = TestClient(app)

MATERIAL = ("Die Verschuldenshaftung nach Art. 41 OR setzt vier Voraussetzungen "
            "voraus: Schaden, Widerrechtlichkeit, Kausalzusammenhang und "
            "Verschulden. Daneben gibt es Kausalhaftungen ohne Verschulden.")


def _cleanup(lesson_id: str):
    p = LESSONS_DIR / f"{lesson_id}.json"
    if p.exists():
        p.unlink()


def test_lektion_erstellen_und_nutzen():
    r = client.post("/api/teacher/lessons", json={
        "titel": "Test-Lektion Haftung",
        "lernziele": ["Voraussetzungen erklären", "Fälle einordnen"],
        "material": MATERIAL,
        "tutor_hinweise": "Arbeite mit Alltagsbeispielen.",
    })
    assert r.status_code == 200
    lesson_id = r.json()["id"]
    try:
        # In der Liste sichtbar
        lessons = client.get("/api/lessons").json()
        assert any(l["id"] == lesson_id for l in lessons)
        # Datei korrekt geschrieben
        data = json.loads((LESSONS_DIR / f"{lesson_id}.json").read_text(encoding="utf-8"))
        assert data["titel"] == "Test-Lektion Haftung"
        assert data["tutor_hinweise"] == "Arbeite mit Alltagsbeispielen."
        assert len(data["einstufungsfragen_fallback"]) == 3
        # Lernende können damit eine Session starten
        s = client.post("/api/session/start",
                        json={"name": "Lernender", "lesson_id": lesson_id})
        assert s.status_code == 200
        assert s.json()["lesson"]["titel"] == "Test-Lektion Haftung"
    finally:
        _cleanup(lesson_id)


def test_slug_ist_eindeutig():
    ids = []
    try:
        for _ in range(2):
            r = client.post("/api/teacher/lessons", json={
                "titel": "Gleicher Titel",
                "lernziele": ["Ziel"],
                "material": MATERIAL,
            })
            ids.append(r.json()["id"])
        assert len(set(ids)) == 2
    finally:
        for i in ids:
            _cleanup(i)


def test_validierung():
    r = client.post("/api/teacher/lessons", json={
        "titel": "", "lernziele": ["Ziel"], "material": MATERIAL})
    assert r.status_code == 400
    r = client.post("/api/teacher/lessons", json={
        "titel": "T", "lernziele": [], "material": MATERIAL})
    assert r.status_code == 400
    r = client.post("/api/teacher/lessons", json={
        "titel": "T", "lernziele": ["Ziel"], "material": "zu kurz"})
    assert r.status_code == 400


def test_lernziele_vorschlag():
    r = client.post("/api/teacher/lessons/suggest-goals", json={"material": MATERIAL})
    assert r.status_code == 200
    d = r.json()
    assert d["titel"] and len(d["lernziele"]) >= 3


def test_quellen_werden_gespeichert():
    r = client.post("/api/teacher/lessons", json={
        "titel": "Lektion mit Quellen",
        "lernziele": ["Ziel"],
        "material": MATERIAL,
        "quellen": [{"name": "skript.pdf", "chars": 1200},
                    {"name": "notizen.docx", "chars": 340}],
    })
    assert r.status_code == 200
    lesson_id = r.json()["id"]
    try:
        data = json.loads((LESSONS_DIR / f"{lesson_id}.json").read_text(encoding="utf-8"))
        assert [q["name"] for q in data["quellen"]] == ["skript.pdf", "notizen.docx"]
        assert data["quellen"][0]["chars"] == 1200
    finally:
        _cleanup(lesson_id)


def test_quellen_sind_optional():
    r = client.post("/api/teacher/lessons", json={
        "titel": "Lektion ohne Quellen", "lernziele": ["Ziel"], "material": MATERIAL})
    assert r.status_code == 200
    lesson_id = r.json()["id"]
    try:
        data = json.loads((LESSONS_DIR / f"{lesson_id}.json").read_text(encoding="utf-8"))
        assert data["quellen"] == []
    finally:
        _cleanup(lesson_id)


def test_text_extraktion_txt():
    r = client.post("/api/teacher/lessons/extract",
                    files={"file": ("material.txt", io.BytesIO(MATERIAL.encode()), "text/plain")})
    assert r.status_code == 200
    assert "Verschuldenshaftung" in r.json()["text"]


def test_extraktion_unbekanntes_format():
    r = client.post("/api/teacher/lessons/extract",
                    files={"file": ("bild.png", io.BytesIO(b"x" * 100), "image/png")})
    assert r.status_code == 400


def test_html_seiten_werden_nicht_gecacht():
    """Ohne no-cache liefert der Browser nach einem Update die alte Oberfläche."""
    for pfad in ("/", "/teacher", "/teacher/lessons/new"):
        r = client.get(pfad)
        assert r.status_code == 200, pfad
        assert r.headers.get("cache-control") == "no-cache", pfad


# ---------------------------------------------------------------- T-07 Verwaltung

from app import llm  # noqa: E402

NEU = ("### Quelle: skript.pdf\n\nDie Tierhalterhaftung nach Art. 56 OR ist eine milde "
       "Kausalhaftung. NEUER-MATERIALTEXT für den Test der Bearbeitung.")


def _lektion(titel="Verwaltung Testlektion"):
    r = client.post("/api/teacher/lessons", json={
        "titel": titel, "lernziele": ["Haftung erklären", "Fälle einordnen"],
        "material": MATERIAL, "quellen": [{"name": "skript.pdf", "chars": 120}]})
    assert r.status_code == 200
    return r.json()["id"]


def test_lektion_ansehen_mit_standard_einstellungen():
    lid = _lektion("Ansehen Testlektion")
    try:
        d = client.get(f"/api/teacher/lessons/{lid}").json()
        assert d["titel"] == "Ansehen Testlektion" and d["version"] == 1
        assert d["quellen"] == [{"name": "skript.pdf", "chars": 120}]
        assert d["einstellungen"] == {"einsatzart": "einfuehrung", "niveauanpassung": "automatisch",
                                      "bewertungsstrenge": "ausgewogen",
                                      "wissensstufen": ["material", "allgemeinwissen"]}
        liste = {l["id"]: l for l in client.get("/api/teacher/lessons").json()}
        assert liste[lid]["lernziele"] == 2 and liste[lid]["quellen"] == 1
        assert liste[lid]["sequenzen"] == 0 and liste[lid]["geaendert_am"]
    finally:
        _cleanup(lid)


def test_bestehende_lektion_ohne_einstellungen_nutzt_standards():
    d = client.get("/api/teacher/lessons/haftungsrecht").json()
    assert d["einstellungen"]["einsatzart"] == "einfuehrung"
    assert d["version"] == 1


def test_lektion_bearbeiten_wirkt_im_naechsten_schritt(monkeypatch):
    lid = _lektion("Bearbeiten Testlektion")
    try:
        lernend = TestClient(app)
        sid = lernend.post("/api/session/start", json={"name": "Bearbeitung", "lesson_id": lid}).json()["session_id"]
        lernend.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
        r = client.put(f"/api/teacher/lessons/{lid}", json={
            "titel": "Bearbeiten Testlektion", "lernziele": ["Haftung erklären"],
            "material": NEU, "quellen": [{"name": "skript.pdf", "chars": 150}],
            "einstellungen": {"bewertungsstrenge": "streng", "einsatzart": "vertiefung"}})
        assert r.status_code == 200
        assert r.json()["version"] == 2 and r.json()["laufend"] == 1
        prompts = []

        def spy(system, user, json_mode=False):
            prompts.append(system)
            return llm._mock_text(system, user), {}
        monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
        lernend.post(f"/api/session/{sid}/next")
        assert "NEUER-MATERIALTEXT" in prompts[-1]
        d = client.get(f"/api/teacher/lessons/{lid}").json()
        assert d["einstellungen"]["bewertungsstrenge"] == "streng"
        assert d["lernziele"] == ["Haftung erklären"] and d["geaendert_am"] >= d["erstellt_am"]
    finally:
        _cleanup(lid)


def test_ungueltige_einstellung_wird_abgelehnt():
    lid = _lektion("Einstellung Testlektion")
    try:
        r = client.put(f"/api/teacher/lessons/{lid}", json={
            "titel": "X", "lernziele": ["y"], "material": MATERIAL,
            "einstellungen": {"bewertungsstrenge": "gnadenlos"}})
        assert r.status_code == 400
    finally:
        _cleanup(lid)


def test_lektion_loeschen_archiviert():
    lid = _lektion("Löschen Testlektion")
    try:
        lernend = TestClient(app)
        sid = lernend.post("/api/session/start", json={"name": "Loeschung", "lesson_id": lid}).json()["session_id"]
        lernend.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
        assert client.delete(f"/api/teacher/lessons/{lid}").status_code == 200
        assert (LESSONS_DIR / f"{lid}.json").exists()         # nicht physisch gelöscht
        assert lid not in [l["id"] for l in client.get("/api/lessons").json()]
        assert lid not in [l["id"] for l in client.get("/api/teacher/lessons").json()]
        archiv = {l["id"]: l for l in client.get("/api/teacher/lessons?archivierte=true").json()}
        assert archiv[lid]["archiviert"] is True
        # Neue Sequenzen gehen nicht mehr, der Lernverlauf bleibt lesbar
        neu = TestClient(app).post("/api/session/start", json={"name": "Spät", "lesson_id": lid})
        assert neu.status_code == 404
        detail = client.get(f"/api/teacher/sessions/{sid}").json()
        assert [e["type"] for e in detail["events"]][:3] == [
            "session_started", "assessment_questions", "assessment_evaluated"]
        assert lernend.get(f"/api/session/{sid}/state").json()["lesson"]["titel"] == "Löschen Testlektion"
        assert client.put(f"/api/teacher/lessons/{lid}", json={
            "titel": "X", "lernziele": ["y"], "material": MATERIAL}).status_code == 409
    finally:
        _cleanup(lid)


def test_verwaltung_ohne_login_gesperrt(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    anonym = TestClient(app)
    assert anonym.get("/api/teacher/lessons").status_code == 401
    assert anonym.get("/api/teacher/lessons/haftungsrecht").status_code == 401
    assert anonym.put("/api/teacher/lessons/haftungsrecht", json={}).status_code == 401
    assert anonym.delete("/api/teacher/lessons/haftungsrecht").status_code == 401
    assert anonym.get("/teacher/lessons", follow_redirects=False).status_code == 307
    assert anonym.get("/teacher/lessons/haftungsrecht/edit", follow_redirects=False).status_code == 307


def test_lektions_id_ohne_pfadtricks():
    assert client.get("/api/teacher/lessons/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/teacher/lessons/Gross").status_code == 404
