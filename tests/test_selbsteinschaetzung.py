"""N-04: Rückmeldung zur Selbsteinschätzung."""

import json

import pytest
from fastapi.testclient import TestClient

from app import llm, tutor
from app.main import app


@pytest.mark.parametrize("sicherheit,bewertung,erwartet", [
    (9, "falsch", "sehr sicher"),
    (8, "falsch", "sehr sicher"),
    (2, "korrekt", "unsicher"),
    (3, "korrekt", "unsicher"),
    (7, "falsch", None),          # keine deutliche Abweichung
    (4, "korrekt", None),
    (9, "korrekt", None),
    (1, "falsch", None),
    (10, "teilweise", None),      # teilweise löst nie etwas aus
    (None, "falsch", None),
])
def test_rueckmeldung_nur_bei_deutlicher_abweichung(sicherheit, bewertung, erwartet):
    r = tutor.selbsteinschaetzung_rueckmeldung(sicherheit, bewertung)
    assert (r is None) if erwartet is None else (erwartet in r and f"{sicherheit} von 10" in r)


def test_kalibrierung_durchschnitte():
    p = {"kalibrierung": [{"confidence": 9, "bewertung": "korrekt"}, {"confidence": 7, "bewertung": "korrekt"},
                          {"confidence": 3, "bewertung": "falsch"}, {"confidence": 4, "bewertung": "teilweise"}]}
    k = tutor.kalibrierung(p)
    assert (k["richtig_avg"], k["falsch_avg"], k["n_richtig"], k["n_falsch"]) == (8.0, 3.5, 2, 2)
    assert "passt gut" in k["deutung"]
    k = tutor.kalibrierung({"kalibrierung": [{"confidence": 8, "bewertung": "falsch"},
                                             {"confidence": 5, "bewertung": "korrekt"}]})
    assert "gleich sicher oder sicherer" in k["deutung"]
    assert tutor.kalibrierung({}) == {"richtig_avg": None, "falsch_avg": None, "n_richtig": 0,
                                      "n_falsch": 0, "deutung": ""}


def _bewertung_nach_laenge(system, user, json_mode=False):
    """Lange Antworten korrekt, kurze falsch (wie der Mock, aber eindeutig)."""
    if "ANTWORT_BEWERTEN" in user:
        antwort = user.split("Antwort des Lernenden: ")[-1].split("\n")[0]
        ok = len(antwort) > 30
        return json.dumps({"elemente": [{"element": "Kern", "status": "korrekt" if ok else "falsch"}],
                           "bewertung": "korrekt" if ok else "falsch",
                           "feedback": "Gut." if ok else "Das stimmt nicht.",
                           "hinweis": "" if ok else "Denk an die Voraussetzungen."}), {}
    return llm._mock_text(system, user), {}


def test_ablauf_mit_zusammenfassung_und_lehrperson(monkeypatch):
    """AK 1: Rückmeldung nur bei deutlicher Abweichung, Zusammenfassung mit beiden
    Durchschnitten, die Lehrperson sieht die Kalibrierung pro Sequenz."""
    monkeypatch.setitem(llm._PROVIDERS, "mock", _bewertung_nach_laenge)
    c = TestClient(app)
    d = c.post("/api/session/start", json={"name": "Kalibrierung"}).json()
    sid = d["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    lang = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."
    plan = [(lang, 9), ("weiss nicht", 9), (lang, 2), (lang, 6)]
    rueckmeldungen = []
    for _ in range(d["total_steps"] * 4):
        t = c.post(f"/api/session/{sid}/next").json()
        if t.get("done"):
            summary = t
            break
        if t["task"]["typ"] != "aufgabe":
            continue
        antwort, sicherheit = plan.pop(0) if plan else (lang, 7)
        r = c.post(f"/api/session/{sid}/answer", json={"answer": antwort, "confidence": sicherheit}).json()
        rueckmeldungen.append(r["selbsteinschaetzung"])
        if r["adaption"] == "retry":     # Nachbesserung ohne neue Sicherheitsangabe
            r = c.post(f"/api/session/{sid}/answer", json={"answer": lang}).json()
            assert r["selbsteinschaetzung"] is None
    else:
        raise AssertionError("Sequenz nicht beendet")
    assert rueckmeldungen[0] is None                          # 9 und richtig: passt
    assert "sehr sicher" in rueckmeldungen[1]                  # 9 und falsch
    assert "unsicher" in rueckmeldungen[2]                     # 2 und richtig
    assert all(x is None for x in rueckmeldungen[3:])          # sonst keine Routine
    k = summary["progress"]["kalibrierung"]
    assert k["falsch_avg"] == 9.0 and k["richtig_avg"] is not None and k["deutung"]
    row = [r for r in c.get("/api/teacher/sessions").json() if r["session_id"] == sid][0]
    assert row["kalibrierung"] == k
    ev = [e for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == "answer_evaluated"]
    assert "sehr sicher" in ev[1]["payload"]["selbsteinschaetzung"] and ev[1]["payload"]["confidence"] == 9
