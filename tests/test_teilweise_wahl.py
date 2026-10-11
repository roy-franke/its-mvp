"""D-07: Lernende entscheiden nach teilweise richtiger Antwort (Entscheid E1)."""

from fastapi.testclient import TestClient

from app import tutor
from app.main import app

TEILWEISE = "Anna haftet, weil Schaden da ist."           # Mock: 15-39 Zeichen
ERGAENZT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


def _bis_teilweise(name):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(4):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    a = c.post(f"/api/session/{sid}/answer", json={"answer": TEILWEISE, "confidence": 6}).json()
    assert a["bewertung"] == "teilweise"
    return c, sid, a


def _events(c, sid, typ):
    return [e["payload"] for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == typ]


def test_ak1_drei_moeglichkeiten_ohne_weiterleitung():
    c, sid, a = _bis_teilweise("Teilweise-1")
    assert [(w["id"], w["label"]) for w in a["wahl"]] == [
        ("ergaenzen", "Antwort ergänzen"), ("loesung", "Lösung ansehen"), ("weiter", "Weiter zur nächsten Aufgabe")]
    assert a["wahl"][0]["haupt"] is True                       # Hauptbutton nach dem ersten «teilweise»
    assert a["progress"]["step"] == 0 and a["adaption_begruendung"] == ""
    assert c.get(f"/api/session/{sid}/state").json()["wartet_auf"] == "wahl_teilweise"


def test_ak2_ergaenzen_mit_bisheriger_antwort():
    c, sid, _ = _bis_teilweise("Teilweise-2")
    e = c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"}).json()
    assert e["ergaenzen"] and e["antwort"] == TEILWEISE
    b = c.post(f"/api/session/{sid}/answer", json={"answer": ERGAENZT}).json()
    assert b["bewertung"] == "korrekt" and b["progress"]["step"] == 1
    assert _events(c, sid, "wahl_nach_teilweise")[0] == {"wahl": "ergaenzen", "ergaenzungen": 0,
                                                         "konzept": "Verschuldenshaftung"}


def test_ak2_loesung_ansehen():
    c, sid, _ = _bis_teilweise("Teilweise-3")
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "loesung"}).json()
    assert d["loesung"].startswith("Anna muss zahlen") and d["progress"]["step"] == 1
    assert d["progress"]["correct"] == 0 and d["progress"]["wrong"] == 0
    assert _events(c, sid, "loesung_gezeigt")


def test_ak2_weiter_zur_naechsten_aufgabe():
    c, sid, _ = _bis_teilweise("Teilweise-4")
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "weiter"}).json()
    assert d["weiter"] and d["progress"]["step"] == 1 and d["progress"]["partial"] == 1
    t = c.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] in ("aufgabe", "theorie")


def test_ak2_grenze_von_drei_ergaenzungen():
    c, sid, a = _bis_teilweise("Teilweise-5")
    for i in range(3):
        assert "ergaenzen" in [w["id"] for w in a["wahl"]]
        c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"})
        a = c.post(f"/api/session/{sid}/answer", json={"answer": TEILWEISE}).json()
        assert a["bewertung"] == "teilweise"
    ids = [w["id"] for w in a["wahl"]]
    assert "ergaenzen" not in ids and ids[-1] == "weiter" and a["wahl"][-1]["haupt"]
    assert c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"}).status_code == 409


def test_ak3_weiter_nach_teilweise_loest_keine_niveauerhoehung_aus():
    p = tutor.new_profile()
    p["level"] = "intermediate"
    k = {"konzept": "Kausalhaftung"}
    tutor.adapt(p, "korrekt", k)
    tutor.adapt(p, "korrekt", k)
    tutor.adapt(p, "teilweise", k)          # danach «Weiter»: Serie beginnt neu
    tutor.adapt(p, "korrekt", k)
    assert not p.get("niveau_frage_offen") and p["serie"] == 1
    assert p["correct"] == 3 and p["wrong"] == 0 and p["partial"] == 1


def test_ak4_pausieren_und_fortsetzen_zeigt_die_wahl():
    c, sid, _ = _bis_teilweise("Teilweise-6")
    c.post(f"/api/session/{sid}/pausieren")
    c2 = TestClient(app)
    c2.post("/api/learner/login", json={"name": "teilweise-6"})
    st = c2.post(f"/api/session/{sid}/fortsetzen").json()
    assert [w["id"] for w in st["wahl"]] == ["ergaenzen", "loesung", "weiter"]


def test_kein_vorabruf_solange_die_wahl_offen_ist():
    c, sid, _ = _bis_teilweise("Teilweise-7")
    assert c.post(f"/api/session/{sid}/next?prefetch=true").json()["vorabruf"] is False
