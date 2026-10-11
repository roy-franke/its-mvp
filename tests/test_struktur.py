"""T-10: Einstufungsfragen robust erzeugen, Strukturfehler allgemein erkennen."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

client = TestClient(app)
LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())


@pytest.fixture
def antwort(monkeypatch):
    """Der Mock liefert für alle Aufrufe dieselbe (falsche) Antwort."""
    def _set(obj):
        text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (text, {}))
    return _set


def test_ak1_objekte_statt_texte_ergeben_drei_lesbare_fragen(antwort):
    antwort({"questions": [{"Frage": "Was ist für dich ein Schaden im Alltag?", "Schwierigkeit": "leicht"},
                           {"question": "Wer haftet, wenn ein Hund ein Velo beschädigt?"},
                           {"text": "Wann muss jemand ohne eigenes Verschulden haften?", "level": 3}]})
    d = tutor.generate_assessment_detail(LESSON)
    assert d["quelle"] == "modell" and not d.get("_fallback")
    assert d["questions"] == ["Was ist für dich ein Schaden im Alltag?",
                              "Wer haftet, wenn ein Hund ein Velo beschädigt?",
                              "Wann muss jemand ohne eigenes Verschulden haften?"]
    assert all(isinstance(q, str) for q in d["questions"])


def test_unbrauchbare_eintraege_werden_verworfen_und_ergaenzt(antwort):
    antwort({"questions": [{"Schwierigkeit": "leicht"}, "", "Wer haftet für einen Hundebiss?"]})
    d = tutor.generate_assessment_detail(LESSON)
    assert len(d["questions"]) == 3 and d["questions"][0] == "Wer haftet für einen Hundebiss?"
    assert d["_fallback"] and d["quelle"] == "lektion"


def test_ak2_leere_liste_ergibt_fallbackfragen_und_event(antwort):
    antwort({"questions": []})
    r = client.post("/api/session/start", json={"name": "Struktur-Einstufung"}).json()
    assert r["questions"] == LESSON["einstufungsfragen_fallback"][:3]
    events = client.get(f"/api/teacher/sessions/{r['session_id']}").json()["events"]
    fb = [e["payload"] for e in events if e["type"] == "fallback_used"]
    assert fb and fb[0]["schrittart"] == "EINSTUFUNGSFRAGEN" and fb[0]["art"] == "struktur"
    assert "Fallback-Fragen der Lektion" in fb[0]["grund"]


def test_ohne_fallbackfragen_aus_den_lernzielen(antwort):
    antwort({"questions": []})
    ohne = {k: v for k, v in LESSON.items() if k != "einstufungsfragen_fallback"}
    d = tutor.generate_assessment_detail(ohne)
    assert d["quelle"] == "lernziele" and len(d["questions"]) == 3
    assert LESSON["lernziele"][0].rstrip(".") in d["questions"][0]


def test_zweiter_versuch_nach_strukturfehler(monkeypatch):
    antworten = iter([json.dumps({"questions": [{"x": 1}]}),
                      json.dumps({"questions": ["Frage eins zum Thema?", "Frage zwei zum Thema?",
                                                "Frage drei zum Thema?"]})])
    prompts = []

    def p(s, u, json_mode=False):
        prompts.append(u)
        return next(antworten), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    d = tutor.generate_assessment_detail(LESSON)
    assert d["quelle"] == "modell" and "KORREKTUR" in prompts[1] and "Falsche Struktur" in prompts[1]


AUFRUFE = {
    "EINSTUFUNG_BEWERTEN": lambda: tutor.evaluate_assessment(LESSON, ["a"], ["b"]),
    "THEORIE_SCHRITT": lambda: tutor.generate_theory(LESSON, tutor.new_profile(), []),
    "NAECHSTE_AUFGABE": lambda: tutor.generate_task(LESSON, dict(tutor.new_profile(), level="advanced"), []),
    "ANTWORT_BEWERTEN": lambda: tutor.evaluate_answer(LESSON, tutor.new_profile(), {"frage": "?"}, "x"),
    "FRAGE_BEANTWORTEN": lambda: tutor.answer_question(LESSON, tutor.new_profile(), None, "Was?", []),
    "ABSCHLUSS": lambda: tutor.generate_summary(LESSON, tutor.new_profile(), []),
    "LERNZIELE_VORSCHLAGEN": lambda: tutor.suggest_goals(LESSON["material"]),
    "MATERIAL_PRUEFEN": lambda: tutor.check_material(["Ziel"], LESSON["material"]),
}

FALSCH = {
    "EINSTUFUNG_BEWERTEN": {"level": ["basic"], "begruendung": "x"},
    "THEORIE_SCHRITT": {"titel": "T", "inhalt": {"absatz": "Text"}, "konzept": "K"},
    "NAECHSTE_AUFGABE": {"inhalt": "Fall", "frage": ["Was?"], "schluesselbegriffe": [{"b": 1}]},
    "ANTWORT_BEWERTEN": {"elemente": ["a", "b"], "bewertung": "korrekt", "feedback": "gut"},
    "FRAGE_BEANTWORTEN": {"antwort": {"text": "x"}},
    "ABSCHLUSS": {"zusammenfassung": "", "erreichte_lernziele": "alle"},
    "LERNZIELE_VORSCHLAGEN": {"lernziele": [{"ziel": "a"}]},
    "MATERIAL_PRUEFEN": {"ziele": "keine"},
}


@pytest.mark.parametrize("schritt", list(AUFRUFE))
def test_ak3_strukturfehler_wird_erkannt_und_protokolliert(schritt, antwort, caplog):
    antwort(FALSCH[schritt])
    llm.reset_timings()
    with caplog.at_level(logging.WARNING, logger="its.llm"):
        AUFRUFE[schritt]()
    meldungen = [r.getMessage() for r in caplog.records if "Strukturfehler" in r.getMessage()]
    assert meldungen and schritt in meldungen[0]
    fb = [f for f in llm.fallbacks() if f["schritt"] == schritt]
    assert fb and "Falsche Struktur" in fb[0]["grund"]


def test_struktur_pruefen_laesst_korrekte_antworten_durch():
    for schritt in didaktik.STRUKTUR:
        mock = llm._mock_text("", f"AUFGABE: {schritt}\nLERNZIELE:\n- a\nMATERIAL:\nx\nFormat:")
        if mock != "{}":
            assert didaktik.struktur_pruefen(json.loads(mock), schritt) is None, schritt
