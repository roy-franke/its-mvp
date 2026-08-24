"""Tests für die ITS-Kernlogik (deterministisch, ohne LLM)."""

from app import tutor
from app.llm import extract_json


def _profile(level="intermediate"):
    p = tutor.new_profile()
    p["level"] = level
    return p


# ---------------------------------------------------------------- Adaption

def test_richtig_geht_weiter():
    p = _profile()
    action, _ = tutor.adapt(p, "korrekt")
    assert action == "next"
    assert p["step"] == 1 and p["correct"] == 1 and p["streak"] == 1


def test_zwei_richtige_erhoehen_level():
    p = _profile("basic")
    tutor.adapt(p, "korrekt")
    action, reason = tutor.adapt(p, "korrekt")
    assert action == "advance"
    assert p["level"] == "intermediate"
    assert reason  # Adaption muss begründet werden
    assert p["streak"] == 0  # Serie beginnt neu


def test_hoechstes_level_bleibt():
    p = _profile("advanced")
    tutor.adapt(p, "korrekt")
    action, _ = tutor.adapt(p, "korrekt")
    assert action == "next"
    assert p["level"] == "advanced"


def test_erster_fehler_gibt_zweiten_versuch():
    p = _profile()
    action, reason = tutor.adapt(p, "falsch")
    assert action == "retry"
    assert reason
    assert p["step"] == 0  # Schritt zählt noch nicht als bearbeitet
    assert p["attempts_current"] == 1


def test_zweiter_fehler_vereinfacht_und_senkt_level():
    p = _profile("intermediate")
    tutor.adapt(p, "falsch")
    action, reason = tutor.adapt(p, "falsch")
    assert action == "simplify"
    assert p["level"] == "basic"
    assert p["step"] == 1  # Schritt gilt als bearbeitet
    assert p["attempts_current"] == 0
    assert "Grundlagen" in reason


def test_tiefstes_level_bleibt():
    p = _profile("basic")
    tutor.adapt(p, "falsch")
    action, _ = tutor.adapt(p, "falsch")
    assert action == "simplify"
    assert p["level"] == "basic"


def test_fehler_unterbricht_serie():
    p = _profile()
    tutor.adapt(p, "korrekt")
    tutor.adapt(p, "falsch")
    assert p["streak"] == 0


def test_richtig_nach_retry_geht_weiter():
    p = _profile()
    tutor.adapt(p, "falsch")          # retry
    action, _ = tutor.adapt(p, "korrekt")
    assert action == "next"
    assert p["step"] == 1
    assert p["attempts_current"] == 0


def test_correct_rate():
    p = _profile()
    assert tutor.correct_rate(p) == 0.0
    tutor.adapt(p, "korrekt")
    tutor.adapt(p, "falsch")
    assert tutor.correct_rate(p) == 0.5


def test_teilweise_gibt_nachbesserung():
    p = _profile()
    action, reason = tutor.adapt(p, "teilweise")
    assert action == "retry"
    assert reason
    assert p["partial"] == 1
    assert p["wrong"] == 0      # zählt nicht als Fehler
    assert p["step"] == 0


def test_teilweise_zweimal_wird_akzeptiert():
    p = _profile()
    tutor.adapt(p, "teilweise")
    action, reason = tutor.adapt(p, "teilweise")
    assert action == "next"
    assert reason
    assert p["step"] == 1
    assert p["correct"] == 1    # wird als bestanden gewertet
    assert p["partial"] == 2


def test_teilweise_dann_korrekt():
    p = _profile()
    tutor.adapt(p, "teilweise")
    action, _ = tutor.adapt(p, "korrekt")
    assert action == "next"
    assert p["step"] == 1 and p["correct"] == 1


def test_teilweise_unterbricht_serie():
    p = _profile("basic")
    tutor.adapt(p, "korrekt")
    tutor.adapt(p, "teilweise")
    assert p["streak"] == 0
    assert p["level"] == "basic"  # kein Level-Aufstieg über teilweise


# ---------------------------------------------------------------- Schrittwahl

def test_sequenz_beginnt_mit_theorie_ausser_advanced():
    for level, expected in [("basic", "theorie"), ("intermediate", "theorie"),
                            ("advanced", "aufgabe")]:
        p = _profile(level)
        assert tutor.decide_step_type(p, None) == expected, level


def test_nie_zwei_theorie_schritte_hintereinander():
    p = _profile("basic")
    p["last_type"] = "theorie"
    assert tutor.decide_step_type(p, None) == "aufgabe"


def test_basic_bekommt_theorie_vor_jedem_konzept():
    p = _profile("basic")
    p["step"] = 3
    p["last_type"] = "aufgabe"
    assert tutor.decide_step_type(p, None) == "theorie"


def test_intermediate_nach_start_direkt_aufgaben():
    p = _profile("intermediate")
    p["step"] = 3
    p["last_type"] = "aufgabe"
    assert tutor.decide_step_type(p, None) == "aufgabe"


def test_simplify_erzwingt_theorie():
    p = _profile("advanced")
    p["step"] = 5
    p["last_type"] = "aufgabe"
    assert tutor.decide_step_type(p, "simplify") == "theorie"


# ---------------------------------------------------------------- JSON-Parsing

def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_mit_text_drumherum():
    assert extract_json('Hier die Antwort:\n{"a": 1}\nGruss') == {"a": 1}


def test_extract_json_codeblock():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_verschachtelt():
    assert extract_json('{"a": {"b": 2}}') == {"a": {"b": 2}}


def test_extract_json_kaputt():
    assert extract_json("kein json") is None
    assert extract_json('{"a": ') is None
