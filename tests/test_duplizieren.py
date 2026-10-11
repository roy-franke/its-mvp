"""T-17: Lektion duplizieren."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _lektion(titel="Duplikat Quelle", **mehr):
    r = client.post("/api/teacher/lessons", json={
        "titel": titel, "lernziele": ["Ziel A", "Ziel B"],
        "material": "### Quelle: skript.pdf\n\n" + "Die Tierhalterhaftung nach Art. 56 OR. " * 6,
        "quellen": [{"name": "skript.pdf", "chars": 240}], "tutor_hinweise": "Alltagsbeispiele",
        "einstellungen": {"bewertungsstrenge": "streng", "einsatzart": "vertiefung"}, **mehr})
    return r.json()["id"]


def test_ak1_kopie_mit_allen_inhalten_neuer_id_ohne_sequenzen():
    lid = _lektion()
    client.post("/api/learner/login", json={"name": "Dup-Lernende"})
    client.post("/api/session/start", json={"lesson_id": lid})
    client.put(f"/api/teacher/lessons/{lid}", json={
        "titel": "Duplikat Quelle", "lernziele": ["Ziel A", "Ziel B"],
        "material": client.get(f"/api/teacher/lessons/{lid}").json()["material"],
        "quellen": [{"name": "skript.pdf", "chars": 240}], "tutor_hinweise": "Alltagsbeispiele",
        "einstellungen": {"bewertungsstrenge": "streng", "einsatzart": "vertiefung"}})
    original = client.get(f"/api/teacher/lessons/{lid}").json()
    assert original["version"] == 2 and original["sequenzen"] == 1
    d = client.post(f"/api/teacher/lessons/{lid}/duplizieren").json()
    assert d["id"] != lid and d["titel"] == "Duplikat Quelle (Kopie)"
    kopie = client.get(f"/api/teacher/lessons/{d['id']}").json()
    for feld in ("lernziele", "material", "quellen", "tutor_hinweise", "einstellungen", "einstufungsfragen_fallback"):
        assert kopie[feld] == original[feld], feld
    assert kopie["version"] == 1 and kopie["sequenzen"] == 0 and not kopie.get("archiviert")


def test_ak2_lernende_sehen_die_kopie_sofort():
    d = client.post(f"/api/teacher/lessons/{_lektion('Duplikat Auswahl')}/duplizieren").json()
    assert d["id"] in [l["id"] for l in client.get("/api/lessons").json()]


def test_archivierte_lektion_duplizieren_ergibt_aktive_kopie():
    lid = _lektion("Duplikat Archiv")
    client.delete(f"/api/teacher/lessons/{lid}")
    d = client.post(f"/api/teacher/lessons/{lid}/duplizieren").json()
    assert not client.get(f"/api/teacher/lessons/{d['id']}").json().get("archiviert")


def test_nur_fuer_lehrpersonen(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    c = TestClient(app)
    assert c.post("/api/teacher/lessons/haftungsrecht/duplizieren").status_code == 401
