"""T-18: Titel manuell, Lernziel-Vorschlag als experimentell."""

from pathlib import Path

from fastapi.testclient import TestClient

from app import llm, tutor
from app.main import app

client = TestClient(app)
MATERIAL = "Die Verschuldenshaftung nach Art. 41 OR verlangt Schaden, Widerrechtlichkeit, Kausalzusammenhang. " * 3


def test_ak1_ohne_titel_kein_vorschlag_und_kein_speichern():
    r = client.post("/api/teacher/lessons/suggest-goals", json={"material": MATERIAL, "titel": "  "})
    assert r.status_code == 400 and "Titel" in r.json()["detail"]
    r = client.post("/api/teacher/lessons", json={"titel": " ", "lernziele": ["Ziel"], "material": MATERIAL})
    assert r.status_code == 400


def test_ak2_titel_steht_im_prompt(monkeypatch):
    prompts = []
    original = llm._PROVIDERS["mock"]
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: prompts.append(u) or original(s, u))
    tutor.suggest_goals(MATERIAL, "Verschuldenshaftung im Strassenverkehr")
    assert "«Verschuldenshaftung im Strassenverkehr»" in prompts[-1]
    assert '"titel"' not in prompts[-1].split("Format:")[1]          # kein Titelvorschlag verlangt


def test_ak3_antwort_ohne_titelvorschlag(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        '{"titel": "Vorschlag", "lernziele": ["a erklären", "b anwenden", "c begründen"]}', {}))
    d = tutor.suggest_goals(MATERIAL, "Haftung")
    assert "titel" not in d and d["lernziele"] == ["a erklären", "b anwenden", "c begründen"]


def test_ak3_editor_kennzeichnet_experimentell():
    html = Path("static/lesson_editor.html").read_text(encoding="utf-8")
    assert 'id="exp-ziele"' in html and "geprüft und ergänzt" in html
    assert "Titel &amp; Lernziele vorschlagen" not in html


def test_t19_materialpruefung_experimentell_und_klare_meldung():
    html = Path("static/lesson_editor.html").read_text(encoding="utf-8")
    assert 'id="exp-check"' in html and html.count('class="experimentell"') >= 2
    assert "Prüfung abgeschlossen. Die Hinweise unten sind Empfehlungen, an deiner Lektion" in html
    assert "Vorschlag übernommen" not in html


def test_t19_pruefung_veraendert_die_lektion_nicht():
    from app.main import load_lesson
    vorher = load_lesson("haftungsrecht")
    r = client.post("/api/teacher/lessons/check-material",
                    json={"lernziele": vorher["lernziele"], "material": vorher["material"]})
    assert r.status_code == 200 and load_lesson("haftungsrecht") == vorher
