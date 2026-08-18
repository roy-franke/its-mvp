"""End-to-End-Tests der API mit Mock-Provider (ohne LLM, ohne laufenden Server)."""

import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ.setdefault("ITS_DB_PATH", "/tmp/its_test.db")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Der Mock-Provider bewertet heuristisch: Antworten ab 40 Zeichen gelten als richtig.
GUTE_ANTWORT = ("Anna haftet, weil Schaden, Widerrechtlichkeit, "
                "Kausalzusammenhang und Verschulden gegeben sind.")
KURZE_ANTWORT = "weiss nicht"


def _start():
    r = client.post("/api/session/start", json={"name": "Testperson"})
    assert r.status_code == 200
    return r.json()


def test_kompletter_durchlauf():
    d = _start()
    sid = d["session_id"]
    assert len(d["questions"]) == 3
    assert d["lesson"]["titel"]

    # Einstufung
    r = client.post(f"/api/session/{sid}/assess",
                    json={"answers": ["a", "b", "c"]}).json()
    assert r["level"] in ("basic", "intermediate", "advanced")
    assert r["begruendung"]

    # Lernschritte bis zum Abschluss (Theorie-Schritte werden nur gelesen)
    finished = False
    theory_seen = 0
    for _ in range(d["total_steps"] * 2 + 4):
        t = client.post(f"/api/session/{sid}/next").json()
        if t.get("done"):
            assert t["summary"]["zusammenfassung"]
            finished = True
            break
        if t["task"].get("typ") == "theorie":
            theory_seen += 1
            assert t["task"]["inhalt"] and "frage" not in t["task"]
            continue
        assert t["task"]["frage"]
        a = client.post(f"/api/session/{sid}/answer",
                        json={"answer": GUTE_ANTWORT}).json()
        assert "korrekt" in a and a["feedback"]
        if a["finished"]:
            t = client.post(f"/api/session/{sid}/next").json()
            assert t["done"] and t["summary"]["zusammenfassung"]
            finished = True
            break
    assert finished
    assert theory_seen >= 1  # Einstieg mit Theorie (Mock stuft intermediate ein)


def test_abschluss_ist_idempotent():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(d["total_steps"] * 2 + 4):
        t = client.post(f"/api/session/{sid}/next").json()
        if t.get("done"):
            break
        if t["task"].get("typ") != "theorie":
            client.post(f"/api/session/{sid}/answer", json={"answer": GUTE_ANTWORT})
    s1 = client.post(f"/api/session/{sid}/next").json()
    s2 = client.post(f"/api/session/{sid}/next").json()
    assert s1["done"] and s2["done"]
    assert s1["summary"] == s2["summary"]
    # Nur ein finished-Event im Log
    events = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert sum(1 for e in events if e["type"] == "finished") == 1


def test_state_fuer_fortsetzen():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    client.post(f"/api/session/{sid}/next")
    st = client.get(f"/api/session/{sid}/state").json()
    assert st["phase"] == "learning"
    assert st["lesson"]["titel"]
    assert st["current_task"] is not None
    assert st["progress"]["total_steps"] == d["total_steps"]


def _next_aufgabe(sid: str) -> dict:
    """Ruft /next auf und überspringt allfällige Theorie-Schritte."""
    for _ in range(4):
        t = client.post(f"/api/session/{sid}/next").json()
        if t.get("done") or t["task"].get("typ") != "theorie":
            return t
    raise AssertionError("Keine Aufgabe erhalten")


def test_falsche_antwort_gibt_retry_dann_simplify():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    _next_aufgabe(sid)
    a1 = client.post(f"/api/session/{sid}/answer", json={"answer": KURZE_ANTWORT}).json()
    assert a1["korrekt"] is False and a1["adaption"] == "retry" and a1["hinweis"]
    a2 = client.post(f"/api/session/{sid}/answer", json={"answer": KURZE_ANTWORT}).json()
    assert a2["adaption"] == "simplify" and a2["adaption_begruendung"]


def test_theorie_schritt_kommt_zuerst_und_ist_unbewertet():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t = client.post(f"/api/session/{sid}/next").json()
    # Mock stuft intermediate ein -> Sequenz beginnt mit Theorie
    assert t["task"]["typ"] == "theorie"
    assert t["progress"]["theory_steps"] == 1
    # Antworten auf Theorie gibt 400
    r = client.post(f"/api/session/{sid}/answer", json={"answer": GUTE_ANTWORT})
    assert r.status_code == 400
    # Danach folgt eine Aufgabe, Theorie zählt nicht als Lernschritt
    t2 = client.post(f"/api/session/{sid}/next").json()
    assert t2["task"]["typ"] == "aufgabe"
    assert t2["progress"]["step"] == 0


def test_nach_simplify_kommt_theorie():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    _next_aufgabe(sid)
    client.post(f"/api/session/{sid}/answer", json={"answer": KURZE_ANTWORT})   # retry
    client.post(f"/api/session/{sid}/answer", json={"answer": KURZE_ANTWORT})   # simplify
    t = client.post(f"/api/session/{sid}/next?adaptation=simplify").json()
    assert t["task"]["typ"] == "theorie"


def test_chat_verstaendnisfrage():
    d = _start()
    sid = d["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    client.post(f"/api/session/{sid}/next")
    r = client.post(f"/api/session/{sid}/chat",
                    json={"message": "Was bedeutet Widerrechtlichkeit genau?"})
    assert r.status_code == 200
    assert r.json()["antwort"]
    # Frage und Antwort landen im Lernverlauf
    events = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    types = [e["type"] for e in events]
    assert "chat_question" in types and "chat_reply" in types


def test_chat_leere_nachricht_gibt_400():
    d = _start()
    sid = d["session_id"]
    r = client.post(f"/api/session/{sid}/chat", json={"message": "   "})
    assert r.status_code == 400


def test_antwort_ohne_aufgabe_gibt_400():
    d = _start()
    sid = d["session_id"]
    r = client.post(f"/api/session/{sid}/answer", json={"answer": "x"})
    assert r.status_code == 400


def test_unbekannte_session_gibt_404():
    assert client.get("/api/session/gibtsnicht/state").status_code == 404


def test_teacher_uebersicht():
    _start()
    rows = client.get("/api/teacher/sessions").json()
    assert rows and {"session_id", "name", "phase", "step", "level"} <= set(rows[0])
