"""T-11: Keine Endlosschleife bei gescheiterter Bewertung."""

from fastapi.testclient import TestClient

from app import tutor
from app.main import app

ANTWORT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."


def _bis_aufgabe(name):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(4):
        t = c.post(f"/api/session/{sid}/next").json()
        if t["task"]["typ"] == "aufgabe":
            return c, sid, t["task"]
    raise AssertionError("keine Aufgabe")


def _events(c, sid, typ):
    return [e["payload"] for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == typ]


def test_ak1_antwort_bleibt_erhalten_und_laesst_sich_erneut_einreichen(monkeypatch):
    c, sid, _ = _bis_aufgabe("Schleife-1")
    monkeypatch.setenv("ITS_MOCK_FAIL", "ANTWORT_BEWERTEN")
    a = c.post(f"/api/session/{sid}/answer", json={"answer": ANTWORT, "confidence": 7}).json()
    assert a["bewertung"] == "unbewertet"
    assert [w["id"] for w in a["wahl"]] == ["nochmals_bewerten"]
    assert a["wahl"][0]["label"] == "Nochmals bewerten lassen"
    st = c.get(f"/api/session/{sid}/state").json()
    assert st["wartet_auf"] == "bewertung_wiederholen" and st["wahl"][0]["id"] == "nochmals_bewerten"
    # Erneut einreichen ohne Neueingabe: Provider funktioniert wieder
    monkeypatch.setenv("ITS_MOCK_FAIL", "")
    b = c.post(f"/api/session/{sid}/wahl", json={"wahl": "nochmals_bewerten"}).json()
    assert b["bewertung"] == "korrekt"
    eingereicht = _events(c, sid, "answer_submitted")
    assert [e["answer"] for e in eingereicht] == [ANTWORT, ANTWORT]
    assert eingereicht[1]["confidence"] == 7           # Sicherheit bleibt erhalten
    assert _events(c, sid, "wahl_nach_bewertungsfehler")[0]["wahl"] == "nochmals_bewerten"


def test_ak2_nach_zweitem_fehler_drei_moeglichkeiten(monkeypatch):
    c, sid, _ = _bis_aufgabe("Schleife-2")
    monkeypatch.setenv("ITS_MOCK_FAIL", "ANTWORT_BEWERTEN")
    a = c.post(f"/api/session/{sid}/answer", json={"answer": ANTWORT}).json()
    b = c.post(f"/api/session/{sid}/wahl", json={"wahl": "nochmals_bewerten"}).json()
    assert b["bewertung"] == "unbewertet" and b["fehler_anzahl"] == 2
    assert [w["id"] for w in b["wahl"]] == ["nochmals_bewerten", "musterloesung", "ohne_bewertung"]
    assert [w["label"] for w in b["wahl"]] == ["Nochmals versuchen", "Musterlösung ansehen und weiter",
                                                "Ohne Bewertung weiter"]
    assert a["feedback"] != b["feedback"]             # nie zweimal dieselbe Meldung
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "ohne_bewertung"}).json()
    assert d["weiter"] and d["progress"]["step"] == 1
    assert d["progress"]["wrong"] == 0 and d["progress"]["correct"] == 0
    t = c.post(f"/api/session/{sid}/next").json()
    assert not t["done"] and t["task"]["typ"] in ("aufgabe", "theorie")


def test_musterloesung_ansehen_und_weiter(monkeypatch):
    c, sid, task = _bis_aufgabe("Schleife-3")
    monkeypatch.setenv("ITS_MOCK_FAIL", "ANTWORT_BEWERTEN")
    c.post(f"/api/session/{sid}/answer", json={"answer": ANTWORT})
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "nochmals_bewerten"})
    d = c.post(f"/api/session/{sid}/wahl", json={"wahl": "musterloesung"}).json()
    assert d["loesung"].startswith("Anna muss zahlen") and d["progress"]["wrong"] == 0


def test_nie_mehr_als_zweimal_dieselbe_meldung():
    texte = [tutor.bewertungsfehler_text(n) for n in range(1, 7)]
    for i in range(len(texte) - 2):
        assert not (texte[i] == texte[i + 1] == texte[i + 2])


def test_pausieren_im_wahlzustand_und_fortsetzen(monkeypatch):
    c, sid, _ = _bis_aufgabe("Schleife-4")
    monkeypatch.setenv("ITS_MOCK_FAIL", "ANTWORT_BEWERTEN")
    c.post(f"/api/session/{sid}/answer", json={"answer": ANTWORT})
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "nochmals_bewerten"})
    assert c.post(f"/api/session/{sid}/pausieren").json()["status"] == "pausiert"
    st = c.post(f"/api/session/{sid}/fortsetzen").json()
    assert st["wartet_auf"] == "wahl_unbewertet"
    assert [w["id"] for w in st["wahl"]] == ["nochmals_bewerten", "musterloesung", "ohne_bewertung"]


def test_ohne_offene_wahl_409():
    c, sid, _ = _bis_aufgabe("Schleife-5")
    assert c.post(f"/api/session/{sid}/wahl", json={"wahl": "ohne_bewertung"}).status_code == 409
