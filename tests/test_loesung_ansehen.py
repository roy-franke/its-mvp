"""D-17: «Lösung ansehen» mit Gegenüberstellung (Auftrag 3, Fall 4 aus Anhang B)."""

from fastapi.testclient import TestClient

from app import didaktik, tutor
from app.main import app

ELEMENTE4 = [{"dimension": "verantwortliche Person", "erwartet": "die Schule, weil sie für die Sicherheit auf dem Schulhof sorgt"},
             {"dimension": "Art der Haftung", "erwartet": "Kausalhaftung"}]
VERSUCH1 = "Der Schüler bzw. seine Eltern. Motorfahrzeughalterhaftung"
VERSUCH5 = "Kausalhaftung, Schule ist haftbar, weil sie für die Sicherheit verantwortlich ist."


def test_abgleich_erkennt_die_uebereinstimmung_aus_fall_4():
    assert didaktik.antwort_deckt_loesung(VERSUCH5, ELEMENTE4)
    assert not didaktik.antwort_deckt_loesung(VERSUCH1, ELEMENTE4)
    assert not didaktik.antwort_deckt_loesung("Die Schule haftet nicht, keine Kausalhaftung.", ELEMENTE4)
    assert not didaktik.antwort_deckt_loesung(VERSUCH5, ["verantwortliche Person", "Art der Haftung"])  # alt


def test_gegenueberstellung_pro_element():
    bewertet = [{"element": "verantwortliche Person", "status": "fehlt", "begruendung": "Die Person fehlt.",
                 "antwort": ""},
                {"element": "Art der Haftung", "status": "korrekt", "antwort": "Kausalhaftung"}]
    g = didaktik.gegenueberstellung(ELEMENTE4, bewertet)
    assert g[0] == {"dimension": "verantwortliche Person", "erwartet": ELEMENTE4[0]["erwartet"], "antwort": "",
                    "status": "fehlt", "begruendung": "Die Person fehlt.", "annahme": ""}
    assert g[1]["antwort"] == "Kausalhaftung" and g[1]["status"] == "korrekt"


def _bis_aufgabe(c, name):
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    return sid


def test_ak1_loesung_zeigt_dimension_erwartet_antwort_status():
    c = TestClient(app)
    sid = _bis_aufgabe(c, "Loesung")
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist.", "confidence": 5})
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "loesung"}).json()
    g = d["gegenueberstellung"]
    assert len(g) == 2 and all(e["dimension"] and e["erwartet"] and e["status"] for e in g)
    assert g[0]["antwort"].startswith("Anna haftet")
    assert "urteil_korrigiert" not in d
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    gezeigt = [e["payload"] for e in events if e["type"] == "loesung_gezeigt"][-1]
    assert gezeigt["gegenueberstellung"] == g                        # AK 3
    verlauf = c.post(f"/api/session/{sid}/fortsetzen").json()["verlauf"]
    assert [e for e in verlauf if e["art"] == "loesung"][-1]["gegenueberstellung"] == g


def test_ak2_uebereinstimmung_korrigiert_das_urteil(monkeypatch):
    """Fall 4: Die Antwort entspricht der Lösung, die Bewertung meldete trotzdem «Person fehlt»."""
    def bewertung(lesson, profile, task, answer, vorher=None, uebernommen=None, zweite_sicht=None):
        return {"bewertung": "teilweise", "korrekt": False, "feedback": "Die verantwortliche Person fehlt.",
                "hinweis": "Wer sorgt für die Sicherheit?",
                "elemente": [{"element": "verantwortliche Person", "status": "fehlt", "antwort": ""},
                             {"element": "Art der Haftung", "status": "korrekt", "antwort": "Kausalhaftung"}]}
    monkeypatch.setattr(tutor, "evaluate_answer", bewertung)
    c = TestClient(app)
    sid = _bis_aufgabe(c, "Fall4")
    from app import store
    s = store.get_session(sid)
    s["profile"]["current_task"]["erwartete_elemente"] = ELEMENTE4
    s["profile"]["current_task"]["erwartete_antwort"] = ("Die Schule ist verantwortlich, weil sie für die Sicherheit "
                                                         "auf dem Schulhof sorgt. Es handelt sich um eine Form der "
                                                         "Kausalhaftung.")
    store.update_session(sid, profile=s["profile"])
    c.post(f"/api/session/{sid}/answer", json={"answer": VERSUCH5, "confidence": 7})
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "loesung"}).json()
    assert "stimmt inhaltlich mit der Lösung überein" in d["urteil_korrigiert"]
    assert d["gegenueberstellung"][0]["status"] == "korrekt" and d["gegenueberstellung"][0]["status_vorher"] == "fehlt"
    p = c.get(f"/api/session/{sid}/state").json()["progress"]
    assert p["correct"] == 1 and p["partial"] == 0
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    k = [e["payload"] for e in events if e["type"] == "urteil_korrigiert"]
    assert k and k[0]["urteil_vorher"] == "teilweise" and k[0]["urteil_nachher"] == "korrekt"
    html = open("static/teacher.html", encoding="utf-8").read()
    assert 'ev.type === "urteil_korrigiert"' in html and 'ev.type === "loesung_gezeigt"' in html
