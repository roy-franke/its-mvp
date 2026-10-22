"""D-19: Erwartete Begründungstiefe passt zur Frage (Auftrag 5).

Grundlage ist die Aufgabe «Unfall in der Bäckerei» aus dem Feedback vom 20.10.2026
(tests/daten/baeckerei.json). Ob das echte Modell die Antwort als korrekt bewertet
(AK 1), prüft tests/eval/eval_didaktik.py; hier wird geprüft, was im Prompt steht
und dass das Urteil aus den Elementen unverändert abgeleitet wird.
"""

import json

from app import llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAECKEREI = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
AUFGABE = BAECKEREI["aufgabe"]
ANTWORT = BAECKEREI["antworten"]["d19"]


def _provider(antworten, prompts):
    it = iter(antworten)

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(it), ensure_ascii=False), {}
    return p


def _bewertung(status, feedback="Das stimmt so.", hinweis=""):
    namen = [e["dimension"] for e in AUFGABE["erwartete_elemente"]]
    return {"elemente": [{"element": n, "status": s, "begruendung": f"{n}: {s}.", "antwort": "Der Bäcker"}
                         for n, s in zip(namen, status)],
            "sachlicher_widerspruch": False, "bewertung": "korrekt", "feedback": feedback, "hinweis": hinweis}


def test_befund_erwartete_elemente_tragen_die_tiefe_der_musterloesung(monkeypatch):
    """Ursache: Die Bewertung erhält den erwarteten Inhalt in der Tiefe der Musterlösung."""
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_bewertung(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, ANTWORT)
    assert "2) Art der Haftung – erwartet: Haftung für Fahrlässigkeit" in prompts[0]


def test_ak2_ak3_massstab_ist_die_tiefe_der_frage(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_bewertung(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, ANTWORT)
    assert tutor.TIEFE_DER_FRAGE in prompts[0]
    assert "nicht an der Tiefe des erwarteten Inhalts" in prompts[0]
    assert "kurze Begründung, die zur Antwort passt und sachlich stimmt" in prompts[0]
    assert "ungenau = sachlich zutreffend, aber allgemeiner, als die Frage es verlangt" in prompts[0]


def test_regel_gilt_auch_ohne_festgelegte_elemente(monkeypatch):
    prompts = []
    alt = dict(AUFGABE, erwartete_elemente=[])
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_bewertung(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), alt, ANTWORT)
    assert tutor.TIEFE_DER_FRAGE in prompts[0]


def test_regel_ist_fachneutral():
    for wort in ("Haftung", "Fahrlässigkeit", "Verschulden", "Bäcker"):
        assert wort not in tutor.TIEFE_DER_FRAGE


def test_ak4_freiwillige_ergaenzung_aendert_das_urteil_nicht(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_bewertung(
        ["korrekt"] * 3, feedback="Richtig, der Bäcker haftet aus Verschulden. Freiwillig könntest du noch die "
                                  "Form des Verschuldens nennen.")], []))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, ANTWORT)
    assert r["bewertung"] == "korrekt"


def test_ak5_falsche_und_fehlende_teile_bleiben_bestehen(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([
        dict(_bewertung(["korrekt", "falsch", "korrekt"]), bewertung="falsch", feedback="Das passt nicht zum Fall."),
        dict(_bewertung(["korrekt", "korrekt", "fehlt"]), bewertung="teilweise", feedback="Es fehlt noch etwas.",
             hinweis="Begründe kurz aus dem Fall.")], []))
    r1 = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, "Der Bäcker. Tierhalterhaftung.")
    r2 = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, "Der Bäcker. Verschuldenshaftung.")
    assert r1["bewertung"] == "falsch"
    assert r2["bewertung"] == "teilweise"


def test_aufgabe_legt_erwarteten_inhalt_in_der_tiefe_der_frage_fest(monkeypatch):
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(dict(AUFGABE), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    tutor.generate_task(LESSON, tutor.new_profile(), [])
    assert "in der Tiefe, die die Frage nennt" in prompts[0]
    assert "feinere Unterscheidungen, nach denen die Frage nicht fragt" in prompts[0]
