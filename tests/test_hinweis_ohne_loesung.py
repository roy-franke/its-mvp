"""D-21: Hinweis und Feedback verraten die erwartete Antwort nicht (Auftrag 5, Entscheid E1).

Testfall ist die Aufgabe «Unfall in der Bäckerei» (tests/daten/baeckerei.json) mit dem im
Feedback vom 20.10.2026 beobachteten Hinweis. Die Läufe mit dem echten Modell (AK 1)
prüft tests/eval/eval_didaktik.py.
"""

import json

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAECKEREI = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
AUFGABE = BAECKEREI["aufgabe"]
TEILWEISE = BAECKEREI["antworten"]["d21_teilweise"]
BEOBACHTET = BAECKEREI["beobachtet"]["hinweis_d20"]
STATUS_TEILWEISE = ["korrekt", "fehlt", "ungenau"]


def _bewertung(status, feedback="Die Person stimmt, die Art der Haftung fehlt noch.",
               hinweis="Überleg, wie der Bäcker mit der gelockerten Schraube umgegangen ist.",
               begruendung="Dazu steht noch nichts."):
    namen = [e["dimension"] for e in AUFGABE["erwartete_elemente"]]
    return {"elemente": [{"element": n, "status": s, "begruendung": begruendung, "antwort": ""}
                         for n, s in zip(namen, status)],
            "sachlicher_widerspruch": False, "bewertung": "teilweise", "feedback": feedback, "hinweis": hinweis}


def _provider(antworten, prompts):
    it = iter(antworten)

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(it), ensure_ascii=False), {}
    return p


def test_ak1_beobachteter_hinweis_wird_beanstandet():
    v = didaktik.loesung_verraten(_bewertung(STATUS_TEILWEISE, hinweis=BEOBACHTET), AUFGABE, [TEILWEISE])
    assert v and "«Fahrlässigkeit»" in v


def test_ak2_schluesselbegriff_im_hinweis_loest_korrektur_aus():
    for hinweis in ("Denk an die Fahrlässigkeit.", "Hat der Bäcker fahrlässig gehandelt?",
                    "Es geht um eine Verschuldenshaftung.", "Überleg, ob das eine Fahrlässigkeitshaftung ist."):
        assert didaktik.loesung_verraten(_bewertung(STATUS_TEILWEISE, hinweis=hinweis), AUFGABE, [TEILWEISE]), hinweis


def test_ak2_woerter_aus_der_antwort_loesen_nichts_aus():
    antwort = "Der Bäcker. Haftung aufgrund von Fahrlässigkeit. Er ist verantwortlich für seine Produkte."
    b = _bewertung(["korrekt", "ungenau", "ungenau"],
                   hinweis="Du schreibst «Haftung aufgrund von Fahrlässigkeit». Begründe das kurz aus dem Fall.",
                   feedback="Du nennst den Bäcker und Fahrlässigkeit. Die Begründung fehlt noch.")
    assert didaktik.loesung_verraten(b, AUFGABE, [antwort]) is None


def test_auch_fruehere_antworten_duerfen_aufgegriffen_werden():
    b = _bewertung(STATUS_TEILWEISE, hinweis="Vorhin hast du von Fahrlässigkeit gesprochen. Wie passt das zum Fall?")
    assert didaktik.loesung_verraten(b, AUFGABE, [TEILWEISE, "Vielleicht Fahrlässigkeit?"]) is None


def test_ak3_feedback_wird_ebenfalls_geprueft():
    b = _bewertung(STATUS_TEILWEISE, feedback="Nenne die Fahrlässigkeit explizit.", hinweis="Lies den Fall nochmals.")
    assert didaktik.loesung_verraten(b, AUFGABE, [TEILWEISE])


def test_angaben_aus_aufgabe_und_fall_sind_erlaubt():
    b = _bewertung(STATUS_TEILWEISE, hinweis="Welche Art der Haftung passt zur gelockerten Schraube in der Maschine?",
                   feedback="Der Bäcker ist richtig. Zur Art der Haftung fehlt noch etwas.")
    assert didaktik.loesung_verraten(b, AUFGABE, [TEILWEISE]) is None


def test_korrekte_antwort_sperrt_nichts():
    assert didaktik.gesperrte_staemme(AUFGABE, [{"status": "korrekt"}] * 3, ["Der Bäcker"]) == set()


def test_begriff_eines_vertretbaren_elements_bleibt_frei():
    """D-15: Bei «vertretbar» darf die erwartete Lösung als naheliegendere Sicht erscheinen."""
    task = {"titel": "T", "inhalt": "Ein Fall.", "frage": "Was gilt?", "schluesselbegriffe": ["Werkeigentümerhaftung"],
            "erwartete_elemente": [{"dimension": "Art", "erwartet": "Werkeigentümerhaftung"},
                                   {"dimension": "Begründung", "erwartet": "mangelhafter Unterhalt"}]}
    gesperrt = didaktik.gesperrte_staemme(task, [{"status": "vertretbar"}, {"status": "fehlt"}], ["Kausalhaftung"])
    assert not didaktik.verratene_woerter("Naheliegender ist die Werkeigentümerhaftung.", gesperrt)
    assert didaktik.verratene_woerter("Denk an den mangelhaften Unterhalt.", gesperrt)


def test_korrekturhinweis_fuehrt_zu_neuem_versuch(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider(
        [_bewertung(STATUS_TEILWEISE, hinweis=BEOBACHTET), _bewertung(STATUS_TEILWEISE)], prompts))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, TEILWEISE)
    assert len(prompts) == 2 and "verraten die erwartete Antwort" in prompts[1]
    assert tutor.OHNE_LOESUNG_REGEL in prompts[0]
    assert "Fahrlässig" not in r["hinweis"] and not r.get("hinweis_ersetzt")


def test_ak4_bleibender_verstoss_wird_ersetzt_ohne_gesperrte_staemme(monkeypatch):
    verraet = _bewertung(STATUS_TEILWEISE, hinweis=BEOBACHTET,
                         feedback="Der Bäcker stimmt. Es fehlt die Haftung für Fahrlässigkeit. Begründe kurz.",
                         begruendung="Fahrlässigkeit ist nicht genannt.")
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([verraet, verraet], []))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), AUFGABE, TEILWEISE)
    gesperrt = didaktik.gesperrte_staemme(AUFGABE, r["elemente"], [TEILWEISE])
    assert r["hinweis_ersetzt"] and r["hinweis"]
    assert not didaktik.verratene_woerter(r["hinweis"], gesperrt)
    assert not didaktik.verratene_woerter(r["feedback"], gesperrt)
    assert r["feedback"] == "Der Bäcker stimmt. Begründe kurz." and r["feedback_gekuerzt"]


def test_ak4_ersatz_auch_wenn_der_ganze_feedbacktext_verraet():
    gesperrt = {"fahrlässig"}
    assert didaktik.ohne_verratene_saetze("Fahrlässigkeit fehlt.", gesperrt) == ""
    assert tutor.hinweis_ohne_loesung([{"element": "Fahrlässigkeit", "status": "fehlt"}], gesperrt) == (
        "Ein Teil deiner Antwort genügt noch nicht. Lies den Fall nochmals und überleg, was er dazu genau hergibt.")


def test_ak5_multiple_choice_bleibt_unveraendert(monkeypatch):
    mc = dict(AUFGABE, aufgabentyp="multiple_choice", optionen=["Haftung für Fahrlässigkeit", "Tierhalterhaftung"])
    b = _bewertung(STATUS_TEILWEISE, hinweis=BEOBACHTET)
    assert didaktik.loesung_verraten(b, mc, ["B"]) is None
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([b], prompts))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), mc, "B")
    assert len(prompts) == 1 and r["hinweis"] == BEOBACHTET and not r.get("hinweis_ersetzt")
