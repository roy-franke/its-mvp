"""N-06: Teaching Mode für Lektionen (Auftrag 5, Entscheide E3 bis E9)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import llm, main, store, tutor
from app.main import app

MATERIAL = ("Die Tierhalterhaftung (Art. 56 OR) macht Halterinnen und Halter für Schäden ihres Tieres haftbar. "
            "Die Werkeigentümerhaftung (Art. 58 OR) gilt für Schäden aus mangelhaftem Unterhalt eines Werks. ") * 4
TIER = {"typ": "aufgabe", "titel": "Hund im Park", "konzept": "Tierhalterhaftung",
        "inhalt": "Ein Hund beisst einen Jogger.", "frage": "Wer haftet und warum?",
        "erwartete_antwort": "Die Halterin nach Art. 56 OR.", "schluesselbegriffe": ["Tierhalterhaftung"],
        "erwartete_elemente": [{"dimension": "Haftung", "erwartet": "Tierhalterhaftung"}]}
WERK = dict(TIER, titel="Ziegel", konzept="Werkeigentümerhaftung", inhalt="Ein Ziegel fällt vom Dach.",
            erwartete_elemente=[{"dimension": "Haftung", "erwartet": "Werkeigentümerhaftung"}])
THEMA_TEXT = "Verlange bei diesem Thema immer den Gesetzesartikel."
LEKTION_TEXT = "Begründe jede Bewertung mit einem Satz aus dem Sachverhalt."


def _lektion(c: TestClient, titel: str) -> str:
    return c.post("/api/teacher/lessons", json={"titel": titel, "lernziele": ["Haftungsarten unterscheiden"],
                                               "material": MATERIAL}).json()["id"]


def _teaching(titel="Teaching Lektion", teaching=True):
    c = TestClient(app)
    lid = _lektion(c, titel)
    d = c.post("/api/session/start", json={"name": "LP Teaching", "lesson_id": lid, "neu_beginnen": True,
                                           "teaching": teaching}).json()
    return c, d, lid


def _anweisung(c, sid, text, geltung, konzept="", schrittart="bewertung", original=""):
    return c.post(f"/api/session/{sid}/anweisung", json={"text": text, "geltung": geltung, "konzept": konzept,
                                                        "schrittart": schrittart, "original": original})


@pytest.fixture
def prompts(monkeypatch):
    """Zeichnet System- und Benutzerteil jedes Aufrufs des Mock-Providers auf."""
    aufrufe = []
    original = llm._PROVIDERS["mock"]

    def p(system, user, json_mode=False):
        aufrufe.append((system, user))
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    # Die Gegenprüfung einer neu erzeugten Aufgabe gälte dem Konzept, das der Mock wählt; sie läuft
    # in _schritte deshalb direkt mit der Aufgabe des Tests
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    return aufrufe


def _schritte(lesson: dict, task: dict) -> None:
    """Bewertung, Gegenprüfung, Verständnisfrage und Aufgabe direkt nach einer Theorie zum Konzept der Aufgabe."""
    tutor.pruefe_musterloesung(lesson, task)
    tutor.evaluate_answer(lesson, tutor.new_profile(), task, "Die Halterin haftet nach dem Gesetz für das Tier.")
    tutor.answer_question(lesson, tutor.new_profile(), task, "Warum ist das so?", [])
    theorie = {"typ": "theorie", "titel": "Theorie", "konzept": task["konzept"], "inhalt": "Erklärung."}
    p = dict(tutor.new_profile(), last_type="theorie", erklaert=[task["konzept"]], covered=[task["konzept"]])
    tutor.generate_task(lesson, p, [{"type": "task", "payload": theorie}])


# ---------------------------------------------------------------- AK 1

def test_ak1_lehrperson_startet_teaching_mode():
    c, d, lid = _teaching()
    assert d["teaching"] is True
    s = store.get_session(d["session_id"])
    assert s["teaching"] == 1 and s["testlauf"] == 1
    assert c.post(f"/api/session/{d['session_id']}/fortsetzen").json()["teaching"] is True


def test_ak1_normaler_testlauf_ohne_teaching():
    c, d, _ = _teaching("Normaler Testlauf", teaching=False)
    assert "teaching" not in d
    assert store.get_session(d["session_id"])["teaching"] == 0
    assert "teaching" not in c.post(f"/api/session/{d['session_id']}/fortsetzen").json()
    r = _anweisung(c, d["session_id"], LEKTION_TEXT, "lektion")
    assert r.status_code == 403


def test_ak1_nicht_fuer_lernende_und_nicht_fuer_archivierte_lektionen(monkeypatch):
    c = TestClient(app)
    lid = _lektion(c, "Archiv Teaching")
    c.delete(f"/api/teacher/lessons/{lid}")
    r = c.post("/api/session/start", json={"name": "LP", "lesson_id": lid, "teaching": True})
    assert r.status_code == 404
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")
    lernende = TestClient(app)
    lernende.post("/api/learner/login", json={"name": "Mia Teaching"})
    r = lernende.post("/api/session/start", json={"lesson_id": "haftungsrecht", "teaching": True})
    assert r.status_code == 403


def test_ak1_start_nur_bei_nicht_archivierten_lektionen():
    html = Path("static/lessons.html").read_text(encoding="utf-8")
    zeile = html[html.index("${l.archiviert ?"):html.index("</div></td>")]
    nicht_archiviert = zeile.split(":", 1)[1]
    assert 'data-act="teaching">Im Teaching Mode testen' in nicht_archiviert
    assert "teaching" not in zeile.split(":", 1)[0]


def test_anweisung_nur_von_der_lehrperson_ihrer_sequenz(monkeypatch):
    c, d, _ = _teaching("Fremde Sequenz")
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim123")
    lernende = TestClient(app)
    lernende.post("/api/learner/login", json={"name": "LP Teaching"})
    assert _anweisung(lernende, d["session_id"], LEKTION_TEXT, "lektion").status_code == 403


# ---------------------------------------------------------------- AK 3

def test_ak3_thema_nur_in_anfragen_zum_selben_konzept(prompts):
    c, d, lid = _teaching("Thema Teaching")
    r = _anweisung(c, d["session_id"], THEMA_TEXT, "thema", konzept="Tierhalterhaftung", schrittart="theorie")
    assert r.status_code == 200
    lesson = main.load_lesson(lid)
    prompts.clear()                      # Einstufungsfragen beim Start gehören zu keinem Konzept
    _schritte(lesson, TIER)
    gleich = list(prompts)
    prompts.clear()
    _schritte(lesson, WERK)
    anders = list(prompts)
    assert len(gleich) >= 3 and all(THEMA_TEXT in u for _, u in gleich)
    assert all("«Tierhalterhaftung»" in u for _, u in gleich)
    assert not any(THEMA_TEXT in u or THEMA_TEXT in s for s, u in anders)
    assert not any(THEMA_TEXT in s for s, _ in gleich)


def test_ak3_konzept_wird_sinngemaess_verglichen():
    lesson = {"tutor_anweisungen": [{"id": "a", "text": THEMA_TEXT, "geltung": "thema", "konzept": "Tierhalterhaftung"}]}
    assert THEMA_TEXT in tutor.anweisungen_zum_thema(lesson, "Die Tierhalterhaftung")
    assert tutor.anweisungen_zum_thema(lesson, "Werkeigentümerhaftung") == ""
    assert tutor.anweisungen_zum_thema(lesson, None) == ""


def test_thema_ohne_konzept_wird_abgelehnt():
    c, d, _ = _teaching("Ohne Konzept")
    assert _anweisung(c, d["session_id"], THEMA_TEXT, "thema", konzept="").status_code == 422


# ---------------------------------------------------------------- AK 4

def test_ak4_lektion_vorschlag_aenderbar_und_im_systemprompt(prompts):
    c, d, lid = _teaching("Lektion Teaching")
    sid = d["session_id"]
    v = c.post(f"/api/session/{sid}/anweisung/vorschlag", json={
        "text": "Hier hättest du den Sachverhalt zitieren sollen.", "konzept": "Tierhalterhaftung",
        "schrittart": "bewertung", "schritt_text": "Richtig, die Halterin haftet."}).json()
    assert v["fallback"] is False and v["vorschlag"].startswith("In dieser Lektion gilt allgemein")
    assert any("AUFGABE: ANWEISUNG_VERALLGEMEINERN" in u for _, u in prompts)
    # Die Lehrperson ändert den Vorschlag und bestätigt ihn
    r = _anweisung(c, sid, LEKTION_TEXT, "lektion", konzept="Tierhalterhaftung",
                   original="Hier hättest du den Sachverhalt zitieren sollen.").json()
    assert r["anweisung"]["text"] == LEKTION_TEXT and r["anweisung"]["original"].startswith("Hier hättest")
    prompts.clear()
    lesson = main.load_lesson(lid)
    _schritte(lesson, TIER)
    _schritte(lesson, WERK)
    tutor.generate_theory(lesson, tutor.new_profile(), [])
    systeme = {s for s, u in prompts}
    assert len(prompts) >= 7 and len(systeme) == 1
    assert LEKTION_TEXT in systeme.pop()
    assert not any(LEKTION_TEXT in u for _, u in prompts)


def test_ak8_verallgemeinerung_scheitert_text_bleibt(monkeypatch):
    monkeypatch.setenv("ITS_MOCK_FAIL", "ANWEISUNG_VERALLGEMEINERN")
    c, d, lid = _teaching("Fallback Teaching")
    text = "Erkläre mit Beispielen aus dem Detailhandel."
    v = c.post(f"/api/session/{d['session_id']}/anweisung/vorschlag", json={"text": text}).json()
    assert v == {"vorschlag": text, "fallback": True, "grund": v["grund"]}
    assert _anweisung(c, d["session_id"], v["vorschlag"], "lektion", original=text).status_code == 200
    assert main.load_lesson(lid)["tutor_anweisungen"][0]["text"] == text


# ---------------------------------------------------------------- AK 5 und AK 6

def test_ak5_ak6_version_editor_loeschen_und_lernverlauf(prompts):
    c, d, lid = _teaching("Version Teaching")
    sid = d["session_id"]
    v0 = c.get(f"/api/teacher/lessons/{lid}").json()["version"]
    a = _anweisung(c, sid, LEKTION_TEXT, "lektion").json()
    b = _anweisung(c, sid, THEMA_TEXT, "thema", konzept="Tierhalterhaftung").json()
    detail = c.get(f"/api/teacher/lessons/{lid}").json()
    assert a["version"] == v0 + 1 and b["version"] == v0 + 2 == detail["version"]
    assert [x["id"] for x in detail["tutor_anweisungen"]] == [a["anweisung"]["id"], b["anweisung"]["id"]]
    assert detail["tutor_hinweise"] == ""
    # AK 6: jede Anweisung steht im Lernverlauf der Teaching-Sequenz
    ereignisse = [e for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == "tutor_anweisung"]
    assert [e["payload"]["text"] for e in ereignisse] == [LEKTION_TEXT, THEMA_TEXT]
    assert ereignisse[1]["payload"]["konzept"] == "Tierhalterhaftung"
    # AK 5: Löschen im Editor, danach in keinem Prompt mehr
    r = c.delete(f"/api/teacher/lessons/{lid}/anweisungen/{a['anweisung']['id']}").json()
    assert r["version"] == v0 + 3 and len(r["tutor_anweisungen"]) == 1
    c.delete(f"/api/teacher/lessons/{lid}/anweisungen/{b['anweisung']['id']}")
    assert c.delete(f"/api/teacher/lessons/{lid}/anweisungen/{b['anweisung']['id']}").status_code == 404
    prompts.clear()
    _schritte(main.load_lesson(lid), TIER)
    assert prompts and not any(LEKTION_TEXT in s + u or THEMA_TEXT in s + u for s, u in prompts)


def test_ak5_anweisungen_bleiben_beim_bearbeiten_im_editor():
    c, d, lid = _teaching("Editor Teaching")
    _anweisung(c, d["session_id"], LEKTION_TEXT, "lektion")
    c.put(f"/api/teacher/lessons/{lid}", json={"titel": "Editor Teaching", "lernziele": ["Ziel"], "material": MATERIAL})
    assert [a["text"] for a in c.get(f"/api/teacher/lessons/{lid}").json()["tutor_anweisungen"]] == [LEKTION_TEXT]


def test_archivierte_lektion_nimmt_keine_anweisungen():
    c, d, lid = _teaching("Archiv nach Start")
    c.delete(f"/api/teacher/lessons/{lid}")
    assert _anweisung(c, d["session_id"], LEKTION_TEXT, "lektion").status_code == 409


# ---------------------------------------------------------------- AK 7

def test_ak7_ohne_anweisungen_sind_die_prompts_gleich(prompts):
    lesson = json.loads(Path("app/lessons/haftungsrecht.json").read_text(encoding="utf-8"))
    assert "tutor_anweisungen" not in lesson
    _schritte(lesson, TIER)
    ohne = list(prompts)
    prompts.clear()
    _schritte(dict(lesson, tutor_anweisungen=[]), TIER)
    leer = list(prompts)
    prompts.clear()
    nur_anderes_thema = [{"id": "x", "text": THEMA_TEXT, "geltung": "thema", "konzept": "Werkeigentümerhaftung"}]
    _schritte(dict(lesson, tutor_anweisungen=nur_anderes_thema), TIER)
    assert ohne == leer == prompts
    assert tutor.anweisungen_zum_thema(lesson, "Tierhalterhaftung") == ""
