"""D-14: Erwartete Elemente mit Inhalt, faire Bewertung von Nachbesserungen (Auftrag 3).

Grundlage ist Fall 4 aus Anhang B (Fahrrad auf dem Schulhof).
"""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())

FALL4 = {
    "typ": "aufgabe", "titel": "Zusammenstoss auf dem Schulhof",
    "inhalt": "Ein Schüler fährt mit seinem Fahrrad auf dem Schulhof. Er biegt plötzlich ab, um einem Ball "
              "auszuweichen und prallt gegen einen anderen Schüler. Der andere Schüler stürzt und verletzt "
              "sich leicht. Die Schule ist für die Sicherheit auf dem Schulhof verantwortlich.",
    "frage": "Nenne die verantwortliche Person und die Art der Haftung, die hier greift.",
    "erwartete_antwort": "Die Schule ist verantwortlich, weil sie für die Sicherheit auf dem Schulhof sorgt. "
                         "Es handelt sich um eine Form der Kausalhaftung.",
    "erwartete_elemente": [
        {"dimension": "verantwortliche Person", "erwartet": "die Schule, weil sie für die Sicherheit auf dem Schulhof sorgt"},
        {"dimension": "Art der Haftung", "erwartet": "Kausalhaftung"}],
    "konzept": "Kausalhaftung",
}
VERSUCHE = ["Der Schüler bzw. seine Eltern. Motorfahrzeughalterhaftung",
            "Kausalhaftung, Schule ist für Sicherheit auf dem Schulhof verantwortlich",
            "Kausalhaftung, Schule ist für Sicherheit auf dem Schulhof verantwortlich und daher haftbar"]


def _bewertung(elemente, hinweis="Überleg, wer für den Schulhof zuständig ist.", bewertung=None):
    return {"elemente": [{"element": n, "status": st, "begruendung": f"{n}: {st}.", "antwort": a}
                         for n, st, a in elemente],
            "sachlicher_widerspruch": False, "bewertung": bewertung or "teilweise",
            "feedback": "Ein Teil stimmt, ein Teil fehlt noch.", "hinweis": hinweis}


def _provider(antworten, prompts):
    it = iter(antworten)

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(it)), {}
    return p


def test_ak1_neue_elemente_mit_inhalt_im_prompt(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([_bewertung(
        [("verantwortliche Person", "korrekt", "Schule"), ("Art der Haftung", "korrekt", "Kausalhaftung")],
        hinweis="")], prompts))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL4, VERSUCHE[1])
    assert "1) verantwortliche Person – erwartet: die Schule, weil sie" in prompts[0]
    assert "sinngemäss aus, nicht wörtlich" in prompts[0]
    assert r["bewertung"] == "korrekt"
    assert r["elemente"][0]["erwartet"].startswith("die Schule") and r["elemente"][0]["begruendung"]


def test_ak1_alte_elemente_als_text_bleiben_gueltig():
    assert didaktik.elemente_normalisieren(["Entscheid", {"dimension": "Art", "erwartet": "Kausal"}]) == [
        {"dimension": "Entscheid", "erwartet": ""}, {"dimension": "Art", "erwartet": "Kausal"}]
    assert didaktik.elemente_bereinigen([{"dimension": "Art", "erwartet": "Kausal"}]) == ["Art"]


def test_ak2_frueherer_falscher_versuch_wirkt_nicht_nach(monkeypatch):
    """Ab Versuch 3 steht Versuch 1 nicht mehr im Prompt; massgeblich ist der Elementstatus."""
    prompts = []
    v1 = _bewertung([("verantwortliche Person", "falsch", "Der Schüler bzw. seine Eltern"),
                     ("Art der Haftung", "falsch", "Motorfahrzeughalterhaftung")], bewertung="falsch")
    v2 = _bewertung([("verantwortliche Person", "korrekt", "Schule"), ("Art der Haftung", "korrekt", "Kausalhaftung")],
                    hinweis="")
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([v1, v2, v2], prompts))
    vorher = []
    for text in VERSUCHE:
        r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL4, text, list(vorher))
        vorher.append({"antwort": text, "bewertung": r["bewertung"], "hinweis": r.get("hinweis", ""),
                       "elemente": r["elemente"]})
    assert "Bisheriger Versuch des Lernenden: Der Schüler" in prompts[1]
    assert "Motorfahrzeughalterhaftung" not in prompts[2]
    assert "verantwortliche Person: korrekt" in prompts[2]
    assert [v["bewertung"] for v in vorher] == ["falsch", "korrekt", "korrekt"]


def test_ak3_frueher_korrektes_element_faellt_nicht_auf_fehlt_zurueck(monkeypatch):
    prompts = []
    zweite = _bewertung([("verantwortliche Person", "fehlt", ""), ("Art der Haftung", "korrekt", "Kausalhaftung")])
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([zweite], prompts))
    vorher = [{"antwort": "Die Schule ist verantwortlich.", "bewertung": "teilweise", "hinweis": "Und die Art?",
               "elemente": [{"element": "verantwortliche Person", "status": "korrekt", "antwort": "Die Schule"},
                            {"element": "Art der Haftung", "status": "fehlt"}]}]
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL4, "Kausalhaftung", vorher)
    person = r["elemente"][0]
    assert person["status"] == "korrekt" and person["aus_frueherem_versuch"] and person["antwort"] == "Die Schule"
    assert r["bewertung"] == "korrekt"


def test_ak4_hinweis_wiederholt_sich_nie(monkeypatch):
    prompts = []
    gleich = _bewertung([("verantwortliche Person", "fehlt", ""), ("Art der Haftung", "korrekt", "Kausalhaftung")],
                        hinweis="Überleg, wer für den Schulhof zuständig ist.")
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([gleich, gleich], prompts))
    vorher = [{"antwort": "Kausalhaftung", "bewertung": "teilweise",
               "hinweis": "Überleg, wer für den Schulhof zuständig ist.",
               "elemente": [{"element": "verantwortliche Person", "status": "fehlt"},
                            {"element": "Art der Haftung", "status": "korrekt"}]}]
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL4, "Kausalhaftung, Haftung", vorher)
    assert "KORREKTUR" in prompts[1] and "wiederholt fast wörtlich" in prompts[1]
    assert didaktik.hinweis_wiederholt(r["hinweis"], [vorher[0]["hinweis"]]) is None
    assert r["hinweis_ersetzt"] and "verantwortliche Person" in r["hinweis"]
    assert "Deine bisherigen Hinweise" in prompts[0] and "Schon beim letzten Versuch ungenügend" in prompts[0]


def test_feedback_spricht_nicht_von_der_musterloesung(monkeypatch):
    prompts = []
    mit = dict(_bewertung([("verantwortliche Person", "fehlt", ""), ("Art der Haftung", "korrekt", "")]),
               feedback="Laut Musterlösung fehlt die verantwortliche Person.")
    ohne = _bewertung([("verantwortliche Person", "fehlt", ""), ("Art der Haftung", "korrekt", "")])
    monkeypatch.setitem(llm._PROVIDERS, "mock", _provider([mit, ohne], prompts))
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL4, "Kausalhaftung")
    assert "Musterlösung" not in r["feedback"] and "Begründe aus dem Fall" in prompts[1]


def test_ak5_lernverlauf_zeigt_status_und_begruendung_pro_versuch():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Begruendung"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist.", "confidence": 5})
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"})
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist."})
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    bew = [e["payload"] for e in events if e["type"] == "answer_evaluated"]
    assert len(bew) == 2 and all(el.get("begruendung") for b in bew for el in b["elemente"])
    assert bew[1]["versuch"] == 2
    # Der Mock wiederholt seinen Hinweis; der zweite Hinweis ist trotzdem ein anderer
    assert bew[0]["hinweis"] != bew[1]["hinweis"]
    html = open("static/teacher.html", encoding="utf-8").read()
    assert "Begründung: ${esc(e.begruendung)}" in html and "Erwartet: ${esc(e.erwartet)}" in html
