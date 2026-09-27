"""Phase 3: deterministische didaktische Prüfungen und ihre Einbindung."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())

# Die Fälle aus den Screenshots 4 und 5 der Testnotizen
THEORIE_HUND = {
    "typ": "theorie", "konzept": "Tierhalterhaftung",
    "inhalt": "Die Tierhalterhaftung (Art. 56 OR) macht Halterinnen und Halter für Schäden "
              "ihres Tieres haftbar.",
    "beispiel": "Beisst ein Hund einen Passanten, haftet die Halterin auch ohne eigenes Verschulden.",
}
SCREENSHOT_4 = {"frage": "Welche Kausalhaftung greift, wenn ein Hund einen Passanten beisst?",
                "inhalt": "", "schluesselbegriffe": ["Kausalhaftung", "Tierhalterhaftung"],
                "erwartete_antwort": "Tierhalterhaftung", "konzept": "Tierhalterhaftung"}
SCREENSHOT_5 = {"frage": "Wer haftet, wenn ein Hund einen Passanten beisst? Begründe mit dem Gesetz.",
                "inhalt": "", "schluesselbegriffe": ["Tierhalterhaftung", "Art. 56 OR"],
                "konzept": "Tierhalterhaftung"}
NEUER_FALL = {"inhalt": "Die Katze von Frau Meier zerkratzt im Treppenhaus das Velo des Nachbarn.",
              "frage": "Wer muss für den Schaden aufkommen, und worauf stützt du dich?",
              "schluesselbegriffe": ["Tierhalterhaftung"], "konzept": "Tierhalterhaftung",
              "erwartete_antwort": "Frau Meier als Halterin haftet nach der Tierhalterhaftung."}


# ---------------------------------------------------------------- Lösungswort

def test_screenshot4_loesungswort_in_frage():
    assert didaktik.loesungswort_in_aufgabe(SCREENSHOT_4)


def test_wortstamm_wird_erkannt():
    task = {"frage": "Welche Haftung greift für Tierhalter?", "schluesselbegriffe": ["Tierhalterhaftung"]}
    assert didaktik.loesungswort_in_aufgabe(task)          # Zusammensetzung
    task = {"frage": "Warum haftet sie?", "schluesselbegriffe": ["Haftung"]}
    assert didaktik.loesungswort_in_aufgabe(task)          # haftet / Haftung


def test_kurze_erwartete_antwort_zaehlt_als_loesungswort():
    task = {"frage": "Welches Prinzip beschreibt die Unschärferelation?", "erwartete_antwort": "Unschärferelation"}
    assert didaktik.loesungswort_in_aufgabe(task)


def test_multiple_choice_ist_ausgenommen():
    mc = dict(SCREENSHOT_4, aufgabentyp="multiple_choice",
              optionen=["Kausalhaftung", "Verschuldenshaftung", "Tierhalterhaftung"])
    assert didaktik.loesungswort_in_aufgabe(mc) is None


def test_neuer_fall_ohne_loesungswort():
    assert didaktik.loesungswort_in_aufgabe(NEUER_FALL) is None


# ---------------------------------------------------------------- Beispiel der Theorie

def test_screenshot5_beispiel_wiederverwendet():
    assert didaktik.beispiel_wiederverwendet(SCREENSHOT_5, THEORIE_HUND)


def test_beispiel_im_fliesstext_wird_ebenfalls_erkannt():
    alt = {"typ": "theorie", "konzept": "Tierhalterhaftung",
           "inhalt": THEORIE_HUND["inhalt"] + " Beispiel: " + THEORIE_HUND["beispiel"]}
    assert didaktik.beispiel_wiederverwendet(SCREENSHOT_5, alt)


def test_neuer_fall_ist_erlaubt():
    assert didaktik.beispiel_wiederverwendet(NEUER_FALL, THEORIE_HUND) is None


def test_ohne_theorie_keine_pruefung():
    assert didaktik.beispiel_wiederverwendet(SCREENSHOT_5, None) is None


# ---------------------------------------------------------------- Abschreibbar

def test_definitionsfrage_direkt_nach_definition():
    assert didaktik.abschreibbar({"frage": "Was ist die Tierhalterhaftung?"}, THEORIE_HUND)
    assert didaktik.pruefe_aufgabe({"frage": "Was ist die Tierhalterhaftung?", "inhalt": ""},
                                   THEORIE_HUND, direkt_nach_theorie=True)


def test_definitionsfrage_spaeter_nicht_geprueft():
    assert didaktik.pruefe_aufgabe({"frage": "Was ist die Tierhalterhaftung?", "inhalt": ""},
                                   THEORIE_HUND, direkt_nach_theorie=False) is None


def test_antwort_woertlich_im_theorietext():
    task = {"frage": "Wofür haften Halterinnen und Halter?",
            "erwartete_antwort": "Halterinnen und Halter haften für Schäden ihres Tieres."}
    assert didaktik.abschreibbar(task, THEORIE_HUND)


def test_anwendungsfrage_nicht_abschreibbar():
    assert didaktik.abschreibbar(NEUER_FALL, THEORIE_HUND) is None


# ---------------------------------------------------------------- Einbindung

def test_verstoss_fuehrt_zu_neugenerierung_mit_hinweis(monkeypatch):
    antworten = iter([json.dumps(dict(SCREENSHOT_5, titel="T")),
                      json.dumps(dict(NEUER_FALL, titel="T"))])
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return next(antworten), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    profil = tutor.new_profile()
    profil["last_type"] = "theorie"
    profil["covered"] = ["Tierhalterhaftung"]
    history = [{"type": "task", "payload": THEORIE_HUND}]
    task = tutor.generate_task(LESSON, profil, history)
    assert task["frage"] == NEUER_FALL["frage"]
    assert "KORREKTUR" in prompts[1] and "Beispiel aus der Theorie" in prompts[1]
    assert "Beisst ein Hund" in prompts[0]       # Theorie-Beispiel im Benutzerteil
    assert task["_verstoesse"]


def test_systemprompt_fuer_alle_schrittarten_gleich(monkeypatch):
    systeme = []

    def spy(system, user, json_mode=False):
        systeme.append(system)
        return llm._mock_text(system, user), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    profil = tutor.new_profile()
    tutor.generate_theory(LESSON, profil, [])
    markiert = dict(THEORIE_HUND, beispiel="EINDEUTIGES-BEISPIEL mit Pony und Reiterin")
    tutor.generate_task(LESSON, profil, [{"type": "task", "payload": markiert}])
    tutor.answer_question(LESSON, profil, None, "Was ist ein Schaden?", [])
    tutor.evaluate_answer(LESSON, profil, {"frage": "x"}, "eine Antwort")
    assert len(set(systeme)) == 1
    assert "DIDAKTISCHE REGELN" in systeme[0]
    assert "EINDEUTIGES-BEISPIEL" not in systeme[0]


def test_musterloesung_nicht_fuer_lernende():
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": "Musterloesung"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        t = c.post(f"/api/session/{sid}/next").json()["task"]
        if t["typ"] == "aufgabe":
            break
    assert "erwartete_antwort" not in t and "schluesselbegriffe" not in t
    assert "erwartete_antwort" not in c.get(f"/api/session/{sid}/state").json()["current_task"]
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    aufgabe = [e for e in events if e["type"] == "task" and e["payload"]["typ"] == "aufgabe"][-1]
    assert aufgabe["payload"]["erwartete_antwort"]      # Lehrperson sieht die Musterlösung


def test_regelverstoss_wird_protokolliert(monkeypatch):
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": "Verstoss"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "theorie"
    # Konzept ist erklärt (D-02 greift nicht), das Lösungswort steht aber in der Frage
    immer_gleich = json.dumps(dict(SCREENSHOT_4, titel="T", konzept="Verschuldenshaftung",
                                   schluesselbegriffe=["Kausalhaftung"]))
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        immer_gleich if "NAECHSTE_AUFGABE" in u else llm._mock_text(s, u), {}))
    c.post(f"/api/session/{sid}/next")
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    v = [e["payload"] for e in events if e["type"] == "regel_verstoss"]
    assert v and v[0]["schrittart"] == "NAECHSTE_AUFGABE" and v[0]["behoben"] is False
    assert "Lösungsbegriff" in v[0]["verstoesse"][0]


@pytest.mark.parametrize("regel", list(didaktik.REGELN))
def test_regelkatalog_vollstaendig(regel):
    r = didaktik.REGELN[regel]
    assert {"paket", "bereich", "titel", "regel", "pruefbar"} <= set(r)
    assert r["regel"] in didaktik.regeln_fuer_prompt()
