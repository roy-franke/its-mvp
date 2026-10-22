"""D-19: The expected depth of reasoning matches the question (order 5).

Based on the task "Unfall in der Bäckerei" from the feedback of 20.10.2026
(tests/daten/baeckerei.json). Whether the real model rates the answer as correct (AK 1)
is checked by tests/eval/eval_didaktik.py; this file checks the prompt and that the
verdict is still derived from the elements unchanged.
"""

import json

from app import llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAKERY = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
TASK = BAKERY["task"]
ANSWER = BAKERY["answers"]["d19"]


def _provider(responses, prompts):
    it = iter(responses)

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(it), ensure_ascii=False), {}
    return provider


def _evaluation(statuses, feedback="Das stimmt so.", hint=""):
    names = [e["dimension"] for e in TASK["erwartete_elemente"]]
    return {"elemente": [{"element": n, "status": s, "begruendung": f"{n}: {s}.", "antwort": "Der Bäcker"}
                         for n, s in zip(names, statuses)],
            "sachlicher_widerspruch": False, "bewertung": "korrekt", "feedback": feedback, "hinweis": hint}


def test_finding_expected_elements_carry_the_depth_of_the_model_solution(monkeypatch):
    """Cause: the evaluation receives the expected content at the depth of the model solution."""
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_evaluation(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, ANSWER)
    assert "2) Art der Haftung – erwartet: Haftung für Fahrlässigkeit" in prompts[0]


def test_ak2_ak3_yardstick_is_the_depth_of_the_question(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_evaluation(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, ANSWER)
    assert tutor.QUESTION_DEPTH_RULE in prompts[0]
    assert "nicht an der Tiefe des erwarteten Inhalts" in prompts[0]
    assert "kurze Begründung, die zur Antwort passt und sachlich stimmt" in prompts[0]
    assert "ungenau = sachlich zutreffend, aber allgemeiner, als die Frage es verlangt" in prompts[0]


def test_rule_applies_without_defined_elements(monkeypatch):
    prompts = []
    old_task = dict(TASK, erwartete_elemente=[])
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_evaluation(["korrekt"] * 3)], prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), old_task, ANSWER)
    assert tutor.QUESTION_DEPTH_RULE in prompts[0]


def test_rule_is_subject_neutral():
    for word in ("Haftung", "Fahrlässigkeit", "Verschulden", "Bäcker"):
        assert word not in tutor.QUESTION_DEPTH_RULE


def test_ak4_optional_addition_does_not_change_the_verdict(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_evaluation(
        ["korrekt"] * 3, feedback="Richtig, der Bäcker haftet aus Verschulden. Freiwillig könntest du noch die "
                                  "Form des Verschuldens nennen.")], []))
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, ANSWER)
    assert result["bewertung"] == "korrekt"


def test_ak5_wrong_and_missing_parts_remain(monkeypatch):
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([
        dict(_evaluation(["korrekt", "falsch", "korrekt"]), bewertung="falsch", feedback="Das passt nicht zum Fall."),
        dict(_evaluation(["korrekt", "korrekt", "fehlt"]), bewertung="teilweise", feedback="Es fehlt noch etwas.",
             hinweis="Begründe kurz aus dem Fall.")], []))
    wrong = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, "Der Bäcker. Tierhalterhaftung.")
    partial = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, "Der Bäcker. Verschuldenshaftung.")
    assert wrong["bewertung"] == "falsch"
    assert partial["bewertung"] == "teilweise"


def test_task_defines_expected_content_at_the_depth_of_the_question(monkeypatch):
    prompts = []

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(dict(TASK), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    tutor.generate_task(LESSON, tutor.new_profile(), [])
    assert "in der Tiefe, die die Frage nennt" in prompts[0]
    assert "feinere Unterscheidungen, nach denen die Frage nicht fragt" in prompts[0]
