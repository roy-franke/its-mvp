"""D-20: Sinngleiche Formulierungen werden akzeptiert (Auftrag 5).

Testfall ist die Aufgabe «Unfall in der Bäckerei» (tests/daten/baeckerei.json).
Ob das echte Modell die Varianten als korrekt bewertet (AK 1, AK 2), prüft
tests/eval/eval_didaktik.py.
"""

import json

import pytest

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAECKEREI = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
AUFGABE = BAECKEREI["aufgabe"]
VARIANTEN = BAECKEREI["antworten"]["d20"]


def _bewertung(art_status, zitat, art_begruendung="Weniger präzise als der Begriff im Material."):
    return {"elemente": [
        {"element": "verantwortliche Person", "status": "korrekt", "begruendung": "Der Bäcker.", "antwort": "Der Bäcker"},
        {"element": "Art der Haftung", "status": art_status, "begruendung": art_begruendung, "antwort": zitat},
        {"element": "kurze Begründung", "status": "korrekt", "begruendung": "Passt.",
         "antwort": "verantwortlich für seine Produkte"}],
        "sachlicher_widerspruch": False, "bewertung": "teilweise" if art_status != "korrekt" else "korrekt",
        "feedback": "Person und Begründung stimmen." if art_status != "korrekt" else "Das stimmt.",
        "hinweis": "Überleg, welche Art von Verschulden der Fall zeigt." if art_status != "korrekt" else ""}


@pytest.mark.parametrize("zitat", ["Haftung aufgrund von Fahrlässigkeit", "Haftung wegen Fahrlässigkeit",
                                   "Fahrlässigkeitshaftung", "Haftung für Fahrlässigkeit"])
def test_ak4_staemme_vorhanden_fuehrt_zur_korrektur(zitat):
    verstoss = didaktik.fachbegriff_trotzdem_ungenau(_bewertung("ungenau", zitat), AUFGABE, zitat)
    assert verstoss and "Art der Haftung" in verstoss and "nicht ungenau" in verstoss


@pytest.mark.parametrize("zitat", ["Der Bäcker haftet", "Haftung", "Er ist schuld"])
def test_ak4_ak3_staemme_fehlen_keine_korrektur(zitat):
    assert didaktik.fachbegriff_trotzdem_ungenau(_bewertung("ungenau", zitat), AUFGABE, zitat) is None


def test_ohne_zitat_zaehlt_die_ganze_antwort():
    b = _bewertung("ungenau", "")
    assert didaktik.fachbegriff_trotzdem_ungenau(b, AUFGABE, VARIANTEN[0])
    assert didaktik.fachbegriff_trotzdem_ungenau(b, AUFGABE, "Der Bäcker haftet.") is None


def test_nur_status_ungenau_wird_geprueft():
    for status in ("korrekt", "fehlt", "falsch"):
        assert didaktik.fachbegriff_trotzdem_ungenau(_bewertung(status, "Haftung wegen Fahrlässigkeit"),
                                                     AUFGABE, VARIANTEN[1]) is None


def test_alte_elemente_ohne_inhalt_werden_nicht_geprueft():
    alt = dict(AUFGABE, erwartete_elemente=["verantwortliche Person", "Art der Haftung", "kurze Begründung"])
    assert didaktik.fachbegriff_trotzdem_ungenau(_bewertung("ungenau", "Haftung wegen Fahrlässigkeit"),
                                                 alt, VARIANTEN[1]) is None


def test_kurzer_erwarteter_inhalt_ohne_schluesselbegriff_wird_nicht_geprueft():
    """Nur Schlüsselbegriffe sind Fachbegriffe; «zuständig für Wartung» ist keiner (D-16 bleibt unberührt)."""
    task = {"schluesselbegriffe": [], "erwartete_elemente": [{"dimension": "Begründung",
                                                              "erwartet": "zuständig für Wartung und Sicherheit"}]}
    b = {"elemente": [{"element": "Begründung", "status": "ungenau", "antwort": "zuständig für Wartung und Sicherheit"}]}
    assert didaktik.fachbegriff_trotzdem_ungenau(b, task, "zuständig für Wartung und Sicherheit") is None


@pytest.mark.parametrize("strenge", ["nachsichtig", "ausgewogen", "streng"])
def test_ak2_regel_steht_bei_jeder_strenge_im_prompt(monkeypatch, strenge):
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(_bewertung("korrekt", VARIANTEN[0]), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    lesson = dict(LESSON, einstellungen={"bewertungsstrenge": strenge})
    tutor.evaluate_answer(lesson, tutor.new_profile(), AUFGABE, VARIANTEN[0])
    assert tutor.GLEICHE_BEDEUTUNG in prompts[0]
    assert "Verlangt ist der Fachbegriff, nicht ein bestimmter Wortlaut" in prompts[0]


def test_korrekturhinweis_fuehrt_zu_neuem_versuch(monkeypatch):
    prompts = []
    antworten = iter([_bewertung("ungenau", "Haftung aufgrund von Fahrlässigkeit"),
                      _bewertung("korrekt", "Haftung aufgrund von Fahrlässigkeit")])

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(antworten), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, VARIANTEN[0])
    assert len(prompts) == 2 and "obwohl die Antwort dazu den Fachbegriff" in prompts[1]
    assert r["bewertung"] == "korrekt"


def test_ak3_ohne_fachbegriff_bleibt_ungenau(monkeypatch):
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(_bewertung("ungenau", "Der Bäcker haftet",
                                     art_begruendung="Die Art der Haftung ist nicht genannt."), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, BAECKEREI["antworten"]["ohne_fachbegriff"])
    assert len(prompts) == 1
    assert r["elemente"][1]["status"] == "ungenau" and r["bewertung"] == "teilweise"
