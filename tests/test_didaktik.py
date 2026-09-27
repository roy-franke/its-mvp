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


# ---------------------------------------------------------------- Befunde aus der Evaluation mit qwen3:30b

HAFTUNG = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BRUCH = json.loads(open("app/lessons/bruchbegriff-verstehen-und-anwenden.json", encoding="utf-8").read())


@pytest.mark.parametrize("lesson,task", [
    (HAFTUNG, {"frage": "Haften die Eltern des verletzten Jugendlichen für die Schäden, die durch das "
                        "Verhalten der Betreuerin entstanden sind?", "schluesselbegriffe": ["Betreuerin"]}),
    (BRUCH, {"inhalt": "Eine Pizza wird in fünf gleich grosse Stücke geteilt.",
             "frage": "Wie viel Pizza bekommt jedes Kind?", "erwartete_antwort": "ein Fünftel"}),
    (BRUCH, {"frage": "Wie viele Gramm Mehl benötigt die Bäckerei, wenn sie 3/4 eines Kilogramms braucht?",
             "schluesselbegriffe": ["3/4 Kilogramm"]}),
])
def test_keine_fehlalarme_beim_loesungswort(lesson, task):
    assert didaktik.loesungswort_in_aufgabe(task, didaktik.fachvokabular(lesson)) is None


def test_screenshot4_bleibt_mit_fachvokabular_erkannt():
    assert didaktik.loesungswort_in_aufgabe(SCREENSHOT_4, didaktik.fachvokabular(HAFTUNG))


def test_abgewandeltes_beispiel_wird_erkannt():
    theorie = {"konzept": "Familienhauptshaftung", "beispiel": "Ein 10-jähriges Kind stösst versehentlich "
               "einen Fahrradfahrer um, weil die Eltern es im Park unbeaufsichtigt gelassen haben."}
    task = {"inhalt": "Ein 12-jähriges Kind läuft alleine auf die Strasse und stösst versehentlich einen "
                      "Fahrradfahrer um. Die Eltern haben es nicht ausreichend beaufsichtigt.",
            "frage": "Müssen die Eltern haften?", "konzept": "Familienhauptshaftung"}
    assert didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(HAFTUNG))


def test_themenwoerter_allein_sind_kein_wiederverwendetes_beispiel():
    theorie = {"konzept": "Verschuldenshaftung", "beispiel": "Beim Fussballspielen zerschlägt jemand "
               "versehentlich eine Fensterscheibe und haftet für den Schaden, weil er fahrlässig war."}
    task = {"inhalt": "Anna putzt das Fenster im zweiten Stock, rutscht von der Leiter und beschädigt "
                      "die Gardine des Nachbarn.", "frage": "Warum haftet Anna für den Schaden?",
            "konzept": "Verschuldenshaftung"}
    assert didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(HAFTUNG)) is None


@pytest.mark.parametrize("text,verstoss", [
    ("Begründen Sie Ihre Antwort.", True),
    ("Wie würden Sie entscheiden?", True),
    ("Begründe deine Antwort.", False),
    ("Sie rutscht von der Leiter. Wer haftet?", False),
])
def test_sie_anrede(text, verstoss):
    assert bool(didaktik.sie_anrede(text)) is verstoss


# ---------------------------------------------------------------- Zweiter Evaluationslauf

QUANTEN = json.loads(open("app/lessons/einfuhrung-in-die-quantenphysik.json", encoding="utf-8").read())
FAMILIE = ("Familienhauptshaftung regelt, dass Eltern für Schäden ihrer Minderjährigen haften, wenn sie "
           "die Aufsichtspflicht verletzen. Dieser Grundsatz ist im Zivilgesetzbuch festgelegt und dient "
           "dem Schutz Dritter vor unzureichender Aufsicht durch die Eltern.")


def test_themenfremde_theorie_wird_erkannt():
    assert didaktik.thema_verfehlt(FAMILIE, BRUCH)
    assert didaktik.thema_verfehlt("Ein Bruch besteht aus Zähler, Bruchstrich und Nenner. Der Nenner "
                                   "zeigt, in wie viele gleich grosse Teile das Ganze geteilt ist, der "
                                   "Zähler, wie viele Teile genommen werden.", BRUCH) is None
    assert didaktik.thema_verfehlt(FAMILIE, HAFTUNG) is None


def test_kurzes_material_wird_nicht_gemessen():
    assert didaktik.thema_verfehlt("Superposition heisst, dass ein Qubit gleichzeitig mehrere Zustände "
                                   "einnehmen kann, was Quantencomputer für Optimierungen nutzen.", QUANTEN) is None


def test_themenwurzel_ist_kein_loesungswort():
    task = {"inhalt": "Ein Rezept für 4 Personen braucht 3/4 kg Mehl.",
            "frage": "Berechne die Menge an Mehl pro Portion in Bruchform.",
            "schluesselbegriffe": ["Bruchform"]}
    assert didaktik.loesungswort_in_aufgabe(task, didaktik.fachvokabular(BRUCH)) is None


def test_angabe_aus_dem_fall_ist_kein_loesungswort():
    task = {"inhalt": "Bei einer Behandlung erleidet ein Patient eine Verletzung durch einen Assistenten.",
            "frage": "Haftet die Praxis für die Verletzung des Patienten?",
            "schluesselbegriffe": ["Verletzung"]}
    assert didaktik.loesungswort_in_aufgabe(task, didaktik.fachvokabular(HAFTUNG)) is None


def test_konzeptwoerter_der_erklaerung_sind_kein_wiederverwendetes_beispiel():
    theorie = {"konzept": "Geschäftsherrenhaftung",
               "inhalt": "Die Geschäftsherrenhaftung macht Arbeitgeber für Sachschäden haftbar, die ihre "
                         "Angestellten bei der Arbeit fahrlässig verursachen.",
               "beispiel": "Ein Angestellter verursacht bei der Arbeit einen Sachschaden, indem er mit dem "
                           "Lastwagen einen Unfall baut."}
    task = {"inhalt": "Ein Pflegefachmann handelt bei der Arbeit fahrlässig und verursacht einen "
                      "Sachschaden an einem Rollstuhl, indem er ihn fallen lässt.",
            "frage": "Warum haftet der Arbeitgeber des Angestellten?", "konzept": "Geschäftsherrenhaftung"}
    assert didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(HAFTUNG)) is None


def test_allgemeine_woerter_sind_kein_wiederverwendetes_beispiel():
    """Dritter Lauf: Klinik-Fall teilte mit dem Beispiel nur «Angestellter», «Gegenstand», «schwer»."""
    theorie = {"konzept": "Geschäftsherrenhaftung",
               "inhalt": "Arbeitgeber haften für Schäden, die ihre Mitarbeiter während der Arbeit verursachen.",
               "beispiel": "Ein Angestellter verursacht bei der Arbeit einen Sachschaden, zum Beispiel durch ein "
                           "versehentliches Umkippen eines schweren Gegenstands, der einem Kunden schadet."}
    task = {"inhalt": "Ein Arzt in einer Klinik vergisst bei einer Operation einen chirurgischen Gegenstand im "
                      "Patienten. Der Patient leidet unter schweren Schäden. Die Klinik, in der der Arzt "
                      "angestellt ist, wird verklagt.", "frage": "Begründe, warum die Klinik haftet.",
            "konzept": "Geschäftsherrenhaftung"}
    assert didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(HAFTUNG)) is None


def test_hundebiss_bleibt_wiederverwendet():
    theorie = {"konzept": "Tierhalterhaftung",
               "inhalt": "Die Tierhalterhaftung ist eine Kausalhaftung des Halters eines Tieres.",
               "beispiel": "Ein Hundebesitzer haftet, wenn sein Hund einen Passanten beisst, auch ohne Fahrlässigkeit."}
    task = {"inhalt": "Ein Schäferhund entkommt aus dem Garten und beisst ein Kind auf dem Schulweg.",
            "frage": "Haftet der Hundebesitzer?", "konzept": "Tierhalterhaftung"}
    assert didaktik.beispiel_wiederverwendet(task, theorie, didaktik.themenwoerter(HAFTUNG))
