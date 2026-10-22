"""D-20: Wording with the same meaning is accepted (order 5).

Test case is the task "Unfall in der Bäckerei" (tests/daten/baeckerei.json).
Whether the real model rates the variants as correct (AK 1, AK 2) is checked by
tests/eval/eval_didaktik.py.
"""

import json

import pytest

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BAKERY = json.loads(open("tests/daten/baeckerei.json", encoding="utf-8").read())
TASK = BAKERY["task"]
VARIANTS = BAKERY["answers"]["d20"]


def _evaluation(type_status, quote, type_reason="Weniger präzise als der Begriff im Material."):
    return {"elemente": [
        {"element": "verantwortliche Person", "status": "korrekt", "begruendung": "Der Bäcker.", "antwort": "Der Bäcker"},
        {"element": "Art der Haftung", "status": type_status, "begruendung": type_reason, "antwort": quote},
        {"element": "kurze Begründung", "status": "korrekt", "begruendung": "Passt.",
         "antwort": "verantwortlich für seine Produkte"}],
        "sachlicher_widerspruch": False, "bewertung": "teilweise" if type_status != "korrekt" else "korrekt",
        "feedback": "Person und Begründung stimmen." if type_status != "korrekt" else "Das stimmt.",
        "hinweis": "Überleg, welche Art von Verschulden der Fall zeigt." if type_status != "korrekt" else ""}


@pytest.mark.parametrize("quote", ["Haftung aufgrund von Fahrlässigkeit", "Haftung wegen Fahrlässigkeit",
                                   "Fahrlässigkeitshaftung", "Haftung für Fahrlässigkeit"])
def test_ak4_stems_present_trigger_a_correction(quote):
    violation = didaktik.key_term_rated_imprecise(_evaluation("ungenau", quote), TASK, quote)
    assert violation and "Art der Haftung" in violation and "nicht ungenau" in violation


@pytest.mark.parametrize("quote", ["Der Bäcker haftet", "Haftung", "Er ist schuld"])
def test_ak4_ak3_stems_missing_no_correction(quote):
    assert didaktik.key_term_rated_imprecise(_evaluation("ungenau", quote), TASK, quote) is None


def test_without_quote_the_whole_answer_counts():
    evaluation = _evaluation("ungenau", "")
    assert didaktik.key_term_rated_imprecise(evaluation, TASK, VARIANTS[0])
    assert didaktik.key_term_rated_imprecise(evaluation, TASK, "Der Bäcker haftet.") is None


def test_only_status_ungenau_is_checked():
    for status in ("korrekt", "fehlt", "falsch"):
        assert didaktik.key_term_rated_imprecise(_evaluation(status, "Haftung wegen Fahrlässigkeit"),
                                                 TASK, VARIANTS[1]) is None


def test_old_elements_without_content_are_not_checked():
    old_task = dict(TASK, erwartete_elemente=["verantwortliche Person", "Art der Haftung", "kurze Begründung"])
    assert didaktik.key_term_rated_imprecise(_evaluation("ungenau", "Haftung wegen Fahrlässigkeit"),
                                             old_task, VARIANTS[1]) is None


def test_short_expected_content_without_key_term_is_not_checked():
    """Only key terms count; "zuständig für Wartung" is none (D-16 stays untouched)."""
    task = {"schluesselbegriffe": [], "erwartete_elemente": [{"dimension": "Begründung",
                                                              "erwartet": "zuständig für Wartung und Sicherheit"}]}
    evaluation = {"elemente": [{"element": "Begründung", "status": "ungenau",
                                "antwort": "zuständig für Wartung und Sicherheit"}]}
    assert didaktik.key_term_rated_imprecise(evaluation, task, "zuständig für Wartung und Sicherheit") is None


@pytest.mark.parametrize("strictness", ["nachsichtig", "ausgewogen", "streng"])
def test_ak2_rule_is_in_the_prompt_for_every_strictness(monkeypatch, strictness):
    prompts = []

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(_evaluation("korrekt", VARIANTS[0]), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    lesson = dict(LESSON, einstellungen={"bewertungsstrenge": strictness})
    tutor.evaluate_answer(lesson, tutor.new_profile(), TASK, VARIANTS[0])
    assert tutor.SAME_MEANING_RULE in prompts[0]
    assert "Verlangt ist der Fachbegriff, nicht ein bestimmter Wortlaut" in prompts[0]


def test_correction_leads_to_a_new_attempt(monkeypatch):
    prompts = []
    responses = iter([_evaluation("ungenau", "Haftung aufgrund von Fahrlässigkeit"),
                      _evaluation("korrekt", "Haftung aufgrund von Fahrlässigkeit")])

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(responses), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, VARIANTS[0])
    assert len(prompts) == 2 and "obwohl die Antwort dazu den Fachbegriff" in prompts[1]
    assert result["bewertung"] == "korrekt"


def test_ak3_without_key_term_stays_imprecise(monkeypatch):
    prompts = []

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(_evaluation("ungenau", "Der Bäcker haftet",
                                      type_reason="Die Art der Haftung ist nicht genannt."), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    result = tutor.evaluate_answer(LESSON, tutor.new_profile(), TASK, BAKERY["answers"]["without_key_term"])
    assert len(prompts) == 1
    assert result["elemente"][1]["status"] == "ungenau" and result["bewertung"] == "teilweise"
