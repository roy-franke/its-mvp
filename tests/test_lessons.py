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
