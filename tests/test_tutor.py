"""Tests für die ITS-Kernlogik (deterministisch, ohne LLM)."""

import pytest

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


def test_keine_erhoehung_ohne_zustimmung():
    """D-04: Drei richtige Antworten zum gleichen Konzept lösen nur eine Frage aus."""
    p = _profile("basic")
    for _ in range(3):
        action, reason = tutor.adapt(p, "korrekt", {"konzept": "Bruch"})
        assert action == "next"
    assert p["level"] == "basic"
    assert p["niveau_frage_offen"] is True
    assert tutor.niveau_entscheid(p, "hoeher_ja", None, "automatisch")[0] == "intermediate"
    assert p["level"] == "intermediate" and not p["niveau_frage_offen"]


def test_konzeptwechsel_setzt_zaehlung_zurueck():
    p = _profile("basic")
    tutor.adapt(p, "korrekt", {"konzept": "A"})
    tutor.adapt(p, "korrekt", {"konzept": "A"})
    tutor.adapt(p, "korrekt", {"konzept": "B"})
    assert not p.get("niveau_frage_offen") and p["serie"] == 1


def test_lieber_so_bleiben():
    p = _profile("basic")
    for _ in range(3):
        tutor.adapt(p, "korrekt", {"konzept": "A"})
    assert tutor.niveau_entscheid(p, "hoeher_nein", None, "automatisch") is None
    assert p["level"] == "basic" and not p["niveau_frage_offen"]
    for _ in range(3):
        tutor.adapt(p, "korrekt", {"konzept": "A"})
    assert not p["niveau_frage_offen"]           # für dieses Konzept nicht nochmals fragen


def test_hoechstes_level_fragt_nicht():
    p = _profile("advanced")
    for _ in range(3):
        tutor.adapt(p, "korrekt", {"konzept": "A"})
    assert not p.get("niveau_frage_offen") and p["level"] == "advanced"


def test_nur_runter_und_fix_fragen_nie():
    for modus in ("nur_runter", "fix"):
        p = _profile("basic")
        for _ in range(4):
            tutor.adapt(p, "korrekt", {"konzept": "A", "niveauanpassung": modus})
        assert not p.get("niveau_frage_offen"), modus


def test_keine_senkung_nach_nur_einem_fehlversuch():
    p = _profile("advanced")
    action, _ = tutor.adapt(p, "falsch")
    assert action == "retry" and p["level"] == "advanced"


def test_teilweise_dann_falsch_senkt_nicht():
    """Ursache aus dem Testlauf: teilweise und danach falsch zählte als zwei Fehler."""
    p = _profile("intermediate")
    tutor.adapt(p, "teilweise")
    action, _ = tutor.adapt(p, "falsch")
    assert action == "simplify" and p["level"] == "intermediate"


def test_senkung_nur_um_eine_stufe():
    p = _profile("advanced")
    tutor.adapt(p, "falsch")
    tutor.adapt(p, "falsch")
    assert p["level"] == "intermediate"         # nie direkt auf basic
    tutor.adapt(p, "falsch")
    tutor.adapt(p, "falsch")
    assert p["level"] == "basic"


def test_festgehaltenes_niveau_bleibt():
    p = _profile("intermediate")
    tutor.niveau_entscheid(p, "festhalten", "intermediate", "automatisch")
    for _ in range(2):
        tutor.adapt(p, "falsch")
    assert p["level"] == "intermediate"
    for _ in range(3):
        tutor.adapt(p, "korrekt", {"konzept": "A"})
    assert p["level"] == "intermediate" and not p.get("niveau_frage_offen")
    tutor.niveau_entscheid(p, "automatisch", None, "automatisch")
    tutor.adapt(p, "falsch")
    tutor.adapt(p, "falsch")
    assert p["level"] == "basic"


def test_fix_aendert_niveau_nie():
    p = _profile("intermediate")
    ctx = {"niveauanpassung": "fix", "konzept": "A"}
    for b in ["falsch", "falsch", "korrekt", "korrekt", "korrekt", "korrekt", "falsch", "falsch"]:
        tutor.adapt(p, b, ctx)
    assert p["level"] == "intermediate"


@pytest.mark.parametrize("text,erwartet", [
    ("Ich möchte auf dem Grundniveau bleiben.", ("halten", "basic")),
    ("Ich möchte aber lieber auf dem Grundniveau bleiben.", ("halten", "basic")),
    ("Kannst du mir einfachere Aufgaben geben?", ("tiefer", None)),
    ("Das ist mir zu einfach", ("hoeher", None)),
    ("Was ist ein Bruch?", None),
])
def test_niveauwunsch_im_chat_erkennen(text, erwartet):
    assert tutor.niveau_wunsch_erkennen(text) == erwartet


def test_niveauwunsch_anwenden():
    p = _profile("intermediate")
    nach, text = tutor.niveau_wunsch_anwenden(p, "halten", "basic", "automatisch")
    assert nach == "basic" and p["niveau_fixiert"] and "Grundlagen" in text
    p = _profile("intermediate")
    nach, text = tutor.niveau_wunsch_anwenden(p, "halten", "basic", "fix")
    assert nach is None and p["level"] == "intermediate" and "fest" in text


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

def test_vertiefung_beginnt_mit_theorie_ausser_advanced():
    for level, expected in [("basic", "theorie"), ("intermediate", "theorie"),
                            ("advanced", "aufgabe")]:
        p = _profile(level)
        assert tutor.decide_step_type(p, None, "vertiefung") == expected, level


def test_einfuehrung_beginnt_immer_mit_theorie():
    for level in tutor.LEVELS:
        assert tutor.decide_step_type(_profile(level), None, "einfuehrung") == "theorie", level


def test_einfuehrung_neue_theorie_nach_zwei_aufgaben():
    p = _profile("advanced")
    p.update(step=3, last_type="aufgabe", erklaert=["Schaden"], aufgaben_seit_theorie=1)
    assert tutor.decide_step_type(p, None, "einfuehrung") == "aufgabe"
    p["aufgaben_seit_theorie"] = 2
    assert tutor.decide_step_type(p, None, "einfuehrung") == "theorie"
    assert tutor.decide_step_type(p, None, "vertiefung") == "aufgabe"


def test_explain_erzwingt_theorie():
    p = _profile("advanced")
    p.update(step=2, last_type="aufgabe")
    assert tutor.decide_step_type(p, "explain", "vertiefung") == "theorie"


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


# ---------------------------------------------------------------- D-02 Einsatzart

def test_vertiefung_falsch_zu_unerklaertem_konzept_gibt_erklaerung():
    p = _profile("advanced")
    action, reason = tutor.adapt(p, "falsch", {"einsatzart": "vertiefung", "konzept_erklaert": False})
    assert action == "explain" and reason
    assert p["level"] == "advanced"        # keine Niveausenkung
    assert p["step"] == 1 and p["attempts_current"] == 0


def test_vertiefung_falsch_zu_erklaertem_konzept_normal():
    p = _profile("advanced")
    action, _ = tutor.adapt(p, "falsch", {"einsatzart": "vertiefung", "konzept_erklaert": True})
    assert action == "retry"


def test_einfuehrung_falsch_gibt_zweiten_versuch():
    p = _profile("advanced")
    action, _ = tutor.adapt(p, "falsch", {"einsatzart": "einfuehrung", "konzept_erklaert": False})
    assert action == "retry"


def test_konzept_erklaert_mit_wortstamm():
    assert tutor.konzept_erklaert("Tierhalterhaftung", ["Tierhalterhaftung Art. 56 OR"])
    assert tutor.konzept_erklaert("Superposition", ["Superpositionsprinzip"])
    assert not tutor.konzept_erklaert("Unschärferelation", ["Welle-Teilchen-Dualismus", "Superposition"])


def test_unerklaerter_begriff_in_erwarteter_antwort():
    task = {"konzept": "Superposition", "schluesselbegriffe": ["Unschärferelation"]}
    texte = "Superposition: Ein Teilchen kann sich in mehreren Zuständen gleichzeitig befinden."
    assert tutor.unerklaert(task, ["Superposition"], texte)
    task["schluesselbegriffe"] = ["Zustände"]
    assert tutor.unerklaert(task, ["Superposition"], texte) is None
