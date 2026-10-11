"""T-12: Wahlmöglichkeiten statt Lückenbüsser bei Fallbacks."""

import pytest
from fastapi.testclient import TestClient

from app import didaktik, tutor
from app.main import app


def _start(name, monkeypatch, fail):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    monkeypatch.setenv("ITS_MOCK_FAIL", fail)
    return c, sid


def _bis_aufgaben_fallback(name, monkeypatch):
    c, sid = _start(name, monkeypatch, "NAECHSTE_AUFGABE")
    t = c.post(f"/api/session/{sid}/next").json()            # Theorie klappt
    assert t["task"]["typ"] == "theorie"
    t = c.post(f"/api/session/{sid}/next").json()            # Aufgabe scheitert
    assert t["task"]["typ"] == "fehler"
    return c, sid, t["task"]


def _events(c, sid, typ):
    return [e["payload"] for e in c.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == typ]


def test_ak1_vier_moeglichkeiten_bei_der_aufgabe(monkeypatch):
    c, sid, task = _bis_aufgaben_fallback("Fallback-Wahl-1", monkeypatch)
    assert task["inhalt"] == "Mir ist gerade keine gute Aufgabe eingefallen. Wie möchtest du weitermachen?"
    assert [w["label"] for w in task["wahl"]] == ["Nochmals versuchen", "Abschnitt in eigenen Worten zusammenfassen",
                                                  "Zum nächsten Thema", "Witz zum Thema"]
    st = c.get(f"/api/session/{sid}/state").json()
    assert st["wartet_auf"] == "wahl_fallback" and len(st["wahl"]) == 4


def test_ak1_nochmals_versuchen(monkeypatch):
    c, sid, _ = _bis_aufgaben_fallback("Fallback-Wahl-2", monkeypatch)
    monkeypatch.setenv("ITS_MOCK_FAIL", "")
    t = c.post(f"/api/session/{sid}/wahl", json={"wahl": "nochmals"}).json()
    assert t["task"]["typ"] == "aufgabe" and not t["task"].get("fallback")


def test_ak1_abschnitt_zusammenfassen(monkeypatch):
    c, sid, _ = _bis_aufgaben_fallback("Fallback-Wahl-3", monkeypatch)
    t = c.post(f"/api/session/{sid}/wahl", json={"wahl": "abschnitt"}).json()
    assert t["task"]["typ"] == "aufgabe" and "eigenen Worten" in t["task"]["frage"]
    assert "Art. 41 OR" in t["task"]["inhalt"] or len(t["task"]["inhalt"]) > 200
    assert didaktik.leere_ankuendigung(t["task"]["inhalt"]) is None


def test_ak1_naechstes_thema_zaehlt_nicht_als_fehler(monkeypatch):
    c, sid, _ = _bis_aufgaben_fallback("Fallback-Wahl-4", monkeypatch)
    t = c.post(f"/api/session/{sid}/wahl", json={"wahl": "naechstes_thema"}).json()
    assert t["task"]["typ"] == "theorie"                       # Einführung: neues Konzept erklären
    assert t["progress"]["wrong"] == 0
    profil = c.get(f"/api/teacher/sessions/{sid}").json()["session"]["profile"]
    assert profil["uebersprungen"] == ["Verschuldenshaftung"]


def test_ak1_witz_und_danach_die_uebrigen_moeglichkeiten(monkeypatch):
    c, sid, _ = _bis_aufgaben_fallback("Fallback-Wahl-5", monkeypatch)
    w = c.post(f"/api/session/{sid}/wahl", json={"wahl": "witz"}).json()
    assert "Mock-Witz" in w["witz"]
    assert [x["id"] for x in w["wahl"]] == ["nochmals", "abschnitt", "naechstes_thema"]
    assert _events(c, sid, "witz")[0]["quelle"] == "modell"


def test_ak2_theorie_mit_eigenen_moeglichkeiten(monkeypatch):
    c, sid = _start("Fallback-Wahl-6", monkeypatch, "THEORIE_SCHRITT")
    t = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "fehler" and t["art"] == "theorie"
    assert [w["label"] for w in t["wahl"]] == ["Nochmals versuchen", "Abschnitt aus dem Material lesen",
                                               "Direkt zur Aufgabe", "Witz zum Thema"]
    a = c.post(f"/api/session/{sid}/wahl", json={"wahl": "abschnitt"}).json()
    assert a["task"]["typ"] == "theorie" and a["task"]["inhalt"].startswith("Hier ist der passende Abschnitt")
    assert len(a["task"]["inhalt"]) > 150


def test_ak2_direkt_zur_aufgabe(monkeypatch):
    c, sid = _start("Fallback-Wahl-7", monkeypatch, "THEORIE_SCHRITT")
    c.post(f"/api/session/{sid}/next")
    a = c.post(f"/api/session/{sid}/wahl", json={"wahl": "direkt_aufgabe"}).json()
    assert a["task"]["typ"] == "aufgabe" and a["task"]["frage"]


def test_ak3_witz_aus_der_liste_wenn_auch_der_aufruf_scheitert(monkeypatch):
    c, sid = _start("Fallback-Wahl-8", monkeypatch, "THEORIE_SCHRITT,WITZ")
    c.post(f"/api/session/{sid}/next")
    w = c.post(f"/api/session/{sid}/wahl", json={"wahl": "witz"}).json()
    assert w["witz"] in tutor.WITZE
    assert _events(c, sid, "witz")[0]["quelle"] == "liste"


def test_ak5_jede_wahl_im_lernverlauf(monkeypatch):
    c, sid, _ = _bis_aufgaben_fallback("Fallback-Wahl-9", monkeypatch)
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "witz"})
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "abschnitt"})
    wahl = _events(c, sid, "wahl_nach_fallback")
    assert [w["wahl"] for w in wahl] == ["witz", "abschnitt"] and wahl[0]["art"] == "aufgabe"


@pytest.mark.parametrize("witz", tutor.WITZE)
def test_witze_ohne_scharfes_s_und_ohne_leere_ankuendigung(witz):
    assert "ß" not in witz and didaktik.leere_ankuendigung(witz) is None
