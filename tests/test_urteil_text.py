"""D-12: Stimmige Rückmeldung zur Selbsteinschätzung, Urteil passt zum Bewertungstext."""

import json

import pytest

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
SCREENSHOT = ("Deine Antwort «ja» ist grundsätzlich richtig, da die Kausalhaftung auch ohne Verschulden greift. "
              "Du hast aber die zentralen Begriffe der Lösung nicht genannt.")
FEHLT = [{"element": "Haftungsart", "status": "fehlt"}, {"element": "Begründung", "status": "fehlt"}]


def test_ak1_teilweise_mit_hoher_sicherheit():
    r = tutor.selbsteinschaetzung_rueckmeldung(10, "teilweise")
    assert r == "Du warst dir sehr sicher (10 von 10), und der Kern stimmte auch. Es fehlte aber noch etwas."
    assert "stimmt aber nicht" not in r


def test_drei_faelle_unterscheiden_sich():
    texte = {b: tutor.selbsteinschaetzung_rueckmeldung(9, b) for b in ("falsch", "teilweise")}
    texte["korrekt"] = tutor.selbsteinschaetzung_rueckmeldung(2, "korrekt")
    assert len(set(texte.values())) == 3 and all(texte.values())


def test_ak2_urteil_falsch_mit_text_grundsaetzlich_richtig_ist_verstoss():
    v = didaktik.urteil_widerspricht_text({"elemente": FEHLT, "bewertung": "teilweise", "feedback": SCREENSHOT})
    assert v and "grundsätzlich richtig" in v


@pytest.mark.parametrize("bewertung,elemente,feedback", [
    ("falsch", FEHLT, "Richtig ist, dass ein Schaden vorliegt, aber die Begründung fehlt."),
    ("falsch", FEHLT, "Das ist noch nicht ganz richtig: Es fehlt die Haftungsart."),
    ("falsch", FEHLT, "Das ist nicht grundsätzlich richtig, weil die Haftung hier entfällt."),
    ("teilweise", [{"element": "a", "status": "korrekt"}, {"element": "b", "status": "fehlt"}], SCREENSHOT),
    ("korrekt", [{"element": "a", "status": "korrekt"}], "Richtig! Genau so ist es."),
])
def test_stimmige_kombinationen_sind_kein_verstoss(bewertung, elemente, feedback):
    assert didaktik.urteil_widerspricht_text({"elemente": elemente, "bewertung": bewertung,
                                              "feedback": feedback}) is None


def test_urteil_korrekt_mit_negativem_text_ist_verstoss():
    assert didaktik.urteil_widerspricht_text({"elemente": [{"element": "a", "status": "korrekt"}],
                                              "feedback": "Das stimmt leider nicht ganz."})


def test_widerspruch_fuehrt_zur_wiederholten_bewertung(monkeypatch):
    antworten = iter([
        {"elemente": FEHLT, "bewertung": "teilweise", "feedback": SCREENSHOT, "hinweis": "Denk an die Haftungsart."},
        {"elemente": [{"element": "Haftungsart", "status": "ungenau"}, {"element": "Begründung", "status": "fehlt"}],
         "bewertung": "teilweise", "feedback": SCREENSHOT, "hinweis": "Denk an die Haftungsart."}])
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(antworten), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), {"frage": "Haftet der Halter? Begründe."}, "ja")
    assert "KORREKTUR" in prompts[1] and "grundsätzlich richtig" in prompts[1]
    assert r["bewertung"] == "teilweise"
