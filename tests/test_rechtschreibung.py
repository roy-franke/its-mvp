"""T-03: Schweizer Rechtschreibung in allen Tutor-Ausgaben."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import llm, tutor
from app.main import app

client = TestClient(app)
ROOT = Path(__file__).resolve().parent.parent


def _mock_mit_eszett(system, user, json_mode=False):
    text = llm._mock_text(system, user)
    return text.replace("Hund", "Hund, der beißt,").replace("Anna", "Anna Weiß"), {}


def test_nachbearbeitung_ersetzt_eszett():
    assert llm.schweizer_rechtschreibung("Der Hund beißt. STRAẞE") == "Der Hund beisst. STRASSE"


def test_gespeicherter_und_ausgelieferter_text_ohne_eszett(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _mock_mit_eszett)
    sid = client.post("/api/session/start", json={"name": "Eszett-Test"}).json()["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    ausgeliefert = []
    for _ in range(3):
        t = client.post(f"/api/session/{sid}/next").json()
        ausgeliefert.append(json.dumps(t, ensure_ascii=False))
        if t["task"]["typ"] == "aufgabe":
            break
    assert any("Weiss" in a for a in ausgeliefert)   # die Mock-Antwort kam wirklich an
    gespeichert = json.dumps(client.get(f"/api/teacher/sessions/{sid}").json(), ensure_ascii=False)
    assert "ß" not in gespeichert and "Weiss" in gespeichert
    assert all("ß" not in a for a in ausgeliefert)


def test_systemprompt_verlangt_schweizer_rechtschreibung():
    lesson = json.loads((ROOT / "app/lessons/haftungsrecht.json").read_text(encoding="utf-8"))
    assert "kein ß, immer ss" in tutor._system_prompt(lesson)


def test_oberflaechentexte_ohne_eszett():
    for f in (ROOT / "static").glob("*.html"):
        assert "ß" not in f.read_text(encoding="utf-8"), f.name


def test_fallback_texte_ohne_eszett():
    assert "ß" not in json.dumps(tutor.FALLBACK_TEXTE, ensure_ascii=False)
