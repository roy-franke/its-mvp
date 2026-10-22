"""D-21: Hint and feedback do not reveal the expected answer (order 5, decision E1).

Test case is the task "Unfall in der Bäckerei" (tests/daten/baeckerei.json) with the hint
observed in the feedback of 20.10.2026. The runs with the real model (AK 1) are checked by
tests/eval/eval_didaktik.py.
"""

import json

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAKERY = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
TASK = BAKERY["task"]
PARTIAL = BAKERY["answers"]["d21_partial"]
OBSERVED = BAKERY["observed"]["hint_d20"]
STATUS_PARTIAL = ["korrekt", "fehlt", "ungenau"]


def _evaluation(statuses, feedback="Die Person stimmt, die Art der Haftung fehlt noch.",
                hint="Überleg, wie der Bäcker mit der gelockerten Schraube umgegangen ist.",
                reason="Dazu steht noch nichts."):
    names = [e["dimension"] for e in TASK["erwartete_elemente"]]
    return {"elemente": [{"element": n, "status": s, "begruendung": reason, "antwort": ""}
                         for n, s in zip(names, statuses)],
            "sachlicher_widerspruch": False, "bewertung": "teilweise", "feedback": feedback, "hinweis": hint}


def _provider(responses, prompts):
    it = iter(responses)

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(it), ensure_ascii=False), {}
    return provider


def test_ak1_observed_hint_is_flagged():
    violation = didaktik.solution_revealed(_evaluation(STATUS_PARTIAL, hint=OBSERVED), TASK, [PARTIAL])
    assert violation and "«Fahrlässigkeit»" in violation


def test_ak2_key_term_in_hint_triggers_correction():
    for hint in ("Denk an die Fahrlässigkeit.", "Hat der Bäcker fahrlässig gehandelt?",
                 "Es geht um eine Verschuldenshaftung.", "Überleg, ob das eine Fahrlässigkeitshaftung ist."):
        assert didaktik.solution_revealed(_evaluation(STATUS_PARTIAL, hint=hint), TASK, [PARTIAL]), hint


def test_ak2_words_from_the_answer_trigger_nothing():
    answer = "Der Bäcker. Haftung aufgrund von Fahrlässigkeit. Er ist verantwortlich für seine Produkte."
    evaluation = _evaluation(["korrekt", "ungenau", "ungenau"],
                             hint="Du schreibst «Haftung aufgrund von Fahrlässigkeit». Begründe das kurz aus dem Fall.",
                             feedback="Du nennst den Bäcker und Fahrlässigkeit. Die Begründung fehlt noch.")
    assert didaktik.solution_revealed(evaluation, TASK, [answer]) is None


def test_earlier_answers_may_be_picked_up():
    evaluation = _evaluation(STATUS_PARTIAL, hint="Vorhin hast du von Fahrlässigkeit gesprochen. Wie passt das zum Fall?")
    assert didaktik.solution_revealed(evaluation, TASK, [PARTIAL, "Vielleicht Fahrlässigkeit?"]) is None


def test_ak3_feedback_is_checked_as_well():
    evaluation = _evaluation(STATUS_PARTIAL, feedback="Nenne die Fahrlässigkeit explizit.", hint="Lies den Fall nochmals.")
    assert didaktik.solution_revealed(evaluation, TASK, [PARTIAL])


def test_details_from_task_and_case_are_allowed():
    evaluation = _evaluation(STATUS_PARTIAL,
                             hint="Welche Art der Haftung passt zur gelockerten Schraube in der Maschine?",
                             feedback="Der Bäcker ist richtig. Zur Art der Haftung fehlt noch etwas.")
    assert didaktik.solution_revealed(evaluation, TASK, [PARTIAL]) is None


def test_correct_answer_blocks_nothing():
    assert didaktik.blocked_stems(TASK, [{"status": "korrekt"}] * 3, ["Der Bäcker"]) == set()


def test_key_term_of_an_acceptable_element_stays_free():
    """D-15: with "vertretbar" the expected solution may appear as the more obvious view."""
    task = {"titel": "T", "inhalt": "Ein Fall.", "frage": "Was gilt?", "schluesselbegriffe": ["Werkeigentümerhaftung"],
            "erwartete_elemente": [{"dimension": "Art", "erwartet": "Werkeigentümerhaftung"},
                                   {"dimension": "Begründung", "erwartet": "mangelhafter Unterhalt"}]}
    blocked = didaktik.blocked_stems(task, [{"status": "vertretbar"}, {"status": "fehlt"}], ["Kausalhaftung"])
    assert not didaktik.revealing_words("Naheliegender ist die Werkeigentümerhaftung.", blocked)
    assert didaktik.revealing_words("Denk an den mangelhaften Unterhalt.", blocked)


def test_correction_leads_to_a_new_attempt(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider(
        [_evaluation(STATUS_PARTIAL, hint=OBSERVED), _evaluation(STATUS_PARTIAL)], prompts))
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, PARTIAL)
    assert len(prompts) == 2 and "verraten die erwartete Antwort" in prompts[1]
    assert tutor.NO_SOLUTION_RULE in prompts[0]
    assert "Fahrlässig" not in result["hinweis"] and not result.get("hinweis_ersetzt")


def test_ak4_remaining_violation_is_replaced_without_blocked_stems(monkeypatch):
    revealing = _evaluation(STATUS_PARTIAL, hint=OBSERVED,
                            feedback="Der Bäcker stimmt. Es fehlt die Haftung für Fahrlässigkeit. Begründe kurz.",
                            reason="Fahrlässigkeit ist nicht genannt.")
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([revealing, revealing], []))
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, PARTIAL)
    blocked = didaktik.blocked_stems(TASK, result["elemente"], [PARTIAL])
    assert result["hinweis_ersetzt"] and result["hinweis"]
    assert not didaktik.revealing_words(result["hinweis"], blocked)
    assert not didaktik.revealing_words(result["feedback"], blocked)
    assert result["feedback"] == "Der Bäcker stimmt. Begründe kurz." and result["feedback_shortened"]


def test_ak4_replacement_when_the_whole_feedback_reveals():
    blocked = {"fahrlässig"}
    assert didaktik.without_revealing_sentences("Fahrlässigkeit fehlt.", blocked) == ""
    assert tutor.hint_without_solution([{"element": "Fahrlässigkeit", "status": "fehlt"}], blocked) == (
        "Ein Teil deiner Antwort genügt noch nicht. Lies den Fall nochmals und überleg, was er dazu genau hergibt.")


def test_ak5_multiple_choice_stays_unchanged(monkeypatch):
    mc = dict(TASK, aufgabentyp="multiple_choice", optionen=["Haftung für Fahrlässigkeit", "Tierhalterhaftung"])
    evaluation = _evaluation(STATUS_PARTIAL, hint=OBSERVED)
    assert didaktik.solution_revealed(evaluation, mc, ["B"]) is None
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([evaluation], prompts))
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), mc, "B")
    assert len(prompts) == 1 and result["hinweis"] == OBSERVED and not result.get("hinweis_ersetzt")
