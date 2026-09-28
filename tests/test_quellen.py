"""N-01: Quellenverweise in Theorieschritten."""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

MATERIAL = (
    "### Quelle: Skript_Haftpflicht.pdf\n\n"
    "Wer einem anderen widerrechtlich Schaden zufügt, muss ihn ersetzen. Dafür braucht es vier "
    "Voraussetzungen: Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden.\n\n"
    "### Quelle: Merkblatt Tierhalter.docx\n\n"
    "Der Halter eines Tieres haftet für den Schaden, den das Tier anrichtet, auch ohne eigenes "
    "Verschulden, sofern er nicht die gebotene Sorgfalt nachweist (Art. 56 OR).\n"
)
LEKTION = {"id": "q", "titel": "Haftpflicht mit Quellen", "lernziele": ["Haftung erklären"],
           "material": MATERIAL}


def test_quellen_aus_dem_material():
    assert didaktik.quellen_der_lektion(LEKTION) == ["Skript_Haftpflicht.pdf", "Merkblatt Tierhalter.docx"]
    assert didaktik.quellen_der_lektion({"material": "ohne Gliederung"}) == []


def test_quelle_pruefen_tolerant_aber_nie_erfunden():
    assert didaktik.quelle_pruefen("Skript_Haftpflicht.pdf", LEKTION) == "Skript_Haftpflicht.pdf"
    assert didaktik.quelle_pruefen("skript haftpflicht", LEKTION) == "Skript_Haftpflicht.pdf"
    assert didaktik.quelle_pruefen("Quelle: Merkblatt Tierhalter", LEKTION) == "Merkblatt Tierhalter.docx"
    assert didaktik.quelle_pruefen("Wikipedia", LEKTION) is None
    assert didaktik.quelle_pruefen("", LEKTION) is None
    assert didaktik.quelle_pruefen(None, LEKTION) is None


def _modell(antwort: dict, prompts: list):
    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(antwort), {}
    return p


THEORIE = {"titel": "Tierhalter", "inhalt": "Der Halter eines Tieres haftet auch ohne Verschulden.",
           "beispiel": "Ein Pferd tritt in einer Reitschule einen Besucher.", "konzept": "Tierhalterhaftung"}


def test_theorie_mit_existierender_quelle(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(dict(THEORIE, quelle="Merkblatt Tierhalter.docx"), prompts))
    t = tutor.generate_theory(LEKTION, tutor.new_profile(), [])
    assert t["quelle"] == "Merkblatt Tierhalter.docx"                       # AK 1
    assert "Skript_Haftpflicht.pdf, Merkblatt Tierhalter.docx" in prompts[0]  # Liste im Benutzerteil


def test_erfundene_quelle_wird_nicht_angezeigt(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(dict(THEORIE, quelle="Lehrbuch OR, S. 42"), []))
    t = tutor.generate_theory(LEKTION, tutor.new_profile(), [])
    assert "quelle" not in t                                                # AK 1
    assert t["quelle_verworfen"] == "Lehrbuch OR, S. 42"
    assert "quelle_verworfen" not in tutor.fuer_lernende(t)


def test_ohne_quellenliste_keine_zeile(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(dict(THEORIE, quelle="irgendwas"), prompts))
    lesson = dict(LEKTION, material=MATERIAL.replace("### Quelle: ", "## "))
    t = tutor.generate_theory(lesson, tutor.new_profile(), [])
    assert "quelle" not in t and "quelle_verworfen" not in t
    assert "Feld quelle" not in prompts[0]


def test_systemprompt_bleibt_gleich():
    """Die Quellenliste steht im Benutzerteil, der Systemprompt ändert sich nicht."""
    assert tutor._system_prompt(LEKTION) == tutor._system_prompt(dict(LEKTION))


def test_fallback_theorie_nennt_die_quelle_des_abschnitts():
    t = tutor.theory_fallback(LEKTION, tutor.new_profile(), None, {"_fehler": "x"})
    assert t["quelle"] in didaktik.quellen_der_lektion(LEKTION)
    abschnitt = t["inhalt"].split("\n\n", 1)[1]
    assert didaktik.quelle_fuer_abschnitt(LEKTION, abschnitt) == t["quelle"]


def test_quelle_kommt_bei_lernenden_an(monkeypatch, tmp_path):
    """Durchstich über die API: Lektion mit Quellen, Theorie zeigt die Quelle."""
    c = TestClient(app)
    import os
    c.post("/api/teacher/login", json={"password": os.getenv("TEACHER_PASSWORD", "")})
    r = c.post("/api/teacher/lessons", json={
        "titel": "Quellen Durchstich", "lernziele": ["Haftung erklären"], "material": MATERIAL,
        "quellen": [{"name": "Skript_Haftpflicht.pdf", "chars": 200},
                    {"name": "Merkblatt Tierhalter.docx", "chars": 200}]})
    assert r.status_code in (200, 201), r.text
    lid = r.json()["id"]
    d = c.post("/api/session/start", json={"name": "Quellen Lernende", "lesson_id": lid}).json()
    sid = d["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(4):
        t = c.post(f"/api/session/{sid}/next").json()["task"]
        if t["typ"] == "theorie":
            assert t["quelle"] == "Skript_Haftpflicht.pdf"
            return
        c.post(f"/api/session/{sid}/answer", json={"answer": "x"})
    raise AssertionError("kein Theorieschritt")
