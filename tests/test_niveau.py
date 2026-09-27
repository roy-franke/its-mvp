"""D-04: Niveausteuerung über die API."""

import pytest
from fastapi.testclient import TestClient

from app.main import LESSONS_DIR, app

GUT = "Anna haftet, weil Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden vorliegen."
KURZ = "weiss nicht"
lp = TestClient(app)


def _start(name, lesson_id="haftungsrecht"):
    c = TestClient(app)
    sid = c.post("/api/session/start", json={"name": name, "lesson_id": lesson_id}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})   # Mock: intermediate
    return c, sid


def _aufgabe(c, sid, adaptation=""):
    for _ in range(4):
        t = c.post(f"/api/session/{sid}/next" + (f"?adaptation={adaptation}" if adaptation else "")).json()
        adaptation = ""
        if t.get("done") or t["task"]["typ"] == "aufgabe":
            return t
    raise AssertionError


def _events(sid, typ):
    return [e["payload"] for e in lp.get(f"/api/teacher/sessions/{sid}").json()["events"] if e["type"] == typ]


def test_chatwunsch_grundniveau_bleiben():
    c, sid = _start("Grundniveau")
    _aufgabe(c, sid)
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ich möchte auf dem Grundniveau bleiben."}).json()
    assert "Grundlagen" in r["antwort"] and "bleiben" in r["antwort"]
    assert r["progress"]["level"] == "basic" and r["progress"]["niveau_fixiert"]
    assert _events(sid, "niveau_wunsch")[0]["nach"] == "basic"
    assert _events(sid, "niveau_geaendert")[0] == {"von": "intermediate", "nach": "basic",
                                                   "grund": "Wunsch der lernenden Person im Chat"}
    # Die folgenden Aufgaben bleiben auf basic, egal wie die Antworten ausfallen
    levels = []
    for antwort in (GUT, GUT, GUT, GUT):
        a = c.post(f"/api/session/{sid}/answer", json={"answer": antwort}).json()
        levels.append(a["progress"]["level"])
        assert a["niveau_frage"] is None
        if a.get("finished"):
            break
        t = _aufgabe(c, sid)
        if t.get("done"):
            break
        levels.append(t["progress"]["level"])
    assert set(levels) == {"basic"}


def test_niveaufrage_nach_drei_richtigen_und_zustimmung():
    c, sid = _start("Zustimmung")
    fragen = []
    for _ in range(3):
        _aufgabe(c, sid)
        a = c.post(f"/api/session/{sid}/answer", json={"answer": GUT}).json()
        fragen.append(a["niveau_frage"])
        assert a["progress"]["level"] == "intermediate"      # nie stillschweigend höher
    assert fragen[:2] == [None, None] and "anspruchsvollere" in fragen[2]
    r = c.post(f"/api/session/{sid}/niveau", json={"aktion": "hoeher_ja"}).json()
    assert r["progress"]["level"] == "advanced"
    assert _events(sid, "niveau_geaendert")[-1]["grund"] == "Zustimmung zu anspruchsvolleren Aufgaben"


def test_lieber_so_bleiben_aendert_nichts():
    c, sid = _start("Bleiben")
    for _ in range(3):
        _aufgabe(c, sid)
        c.post(f"/api/session/{sid}/answer", json={"answer": GUT})
    r = c.post(f"/api/session/{sid}/niveau", json={"aktion": "hoeher_nein"}).json()
    assert r["progress"]["level"] == "intermediate" and not r["progress"]["niveau_frage_offen"]


def test_niveau_selbst_festhalten_und_freigeben():
    c, sid = _start("Festhalten")
    _aufgabe(c, sid)
    r = c.post(f"/api/session/{sid}/niveau", json={"aktion": "festhalten", "level": "advanced"}).json()
    assert r["progress"]["level"] == "advanced" and r["progress"]["niveau_fixiert"]
    c.post(f"/api/session/{sid}/answer", json={"answer": KURZ})
    a = c.post(f"/api/session/{sid}/answer", json={"answer": KURZ}).json()
    assert a["adaption"] == "simplify" and a["progress"]["level"] == "advanced"
    r = c.post(f"/api/session/{sid}/niveau", json={"aktion": "automatisch"}).json()
    assert not r["progress"]["niveau_fixiert"]


def test_senkung_erst_nach_zweitem_fehlversuch_und_nur_eine_stufe():
    c, sid = _start("Senkung")
    _aufgabe(c, sid)
    c.post(f"/api/session/{sid}/niveau", json={"aktion": "festhalten", "level": "advanced"})
    c.post(f"/api/session/{sid}/niveau", json={"aktion": "automatisch"})
    a1 = c.post(f"/api/session/{sid}/answer", json={"answer": KURZ}).json()
    assert a1["progress"]["level"] == "advanced"
    a2 = c.post(f"/api/session/{sid}/answer", json={"answer": KURZ}).json()
    assert a2["progress"]["level"] == "intermediate"


@pytest.fixture
def fix_lektion():
    r = lp.post("/api/teacher/lessons", json={
        "titel": "Fixes Niveau", "lernziele": ["Haftung erklären"],
        "material": ("Die Verschuldenshaftung nach Art. 41 OR verlangt Schaden, Widerrechtlichkeit, "
                     "Kausalzusammenhang und Verschulden. ") * 2,
        "einstellungen": {"niveauanpassung": "fix"}})
    lid = r.json()["id"]
    yield lid
    (LESSONS_DIR / f"{lid}.json").unlink(missing_ok=True)


def test_fix_niveau_bleibt_waehrend_der_ganzen_sequenz(fix_lektion):
    c, sid = _start("Fix", fix_lektion)
    levels = set()
    antworten = [GUT, GUT, GUT, KURZ, KURZ, GUT, KURZ, KURZ, GUT, GUT]
    t = _aufgabe(c, sid)
    for antwort in antworten:
        a = c.post(f"/api/session/{sid}/answer", json={"answer": antwort}).json()
        levels.add(a["progress"]["level"])
        assert a["niveau_frage"] is None
        if a["adaption"] != "retry":
            if a["finished"]:
                break
            t = _aufgabe(c, sid, a["adaption"] if a["adaption"] in ("simplify", "explain") else "")
            if t.get("done"):
                break
            levels.add(t["progress"]["level"])
    assert levels == {"intermediate"}
    r = c.post(f"/api/session/{sid}/niveau", json={"aktion": "festhalten", "level": "basic"})
    assert r.status_code == 409
    chat = c.post(f"/api/session/{sid}/chat", json={"message": "Ich möchte auf dem Grundniveau bleiben"}).json()
    assert "fest" in chat["antwort"] and chat["progress"]["level"] == "intermediate"
