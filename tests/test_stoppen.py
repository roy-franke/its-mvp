"""T-28: Bearbeitung einer Anfrage stoppen."""

import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import abbruch, llm
from app.main import app


def _sequenz(name):
    s = TestClient(app)
    s.post("/api/learner/login", json={"name": name})
    sid = s.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True}).json()["session_id"]
    s.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    s.post(f"/api/session/{sid}/next")                  # Theorie
    s.post(f"/api/session/{sid}/next")                  # Aufgabe
    return s, sid


def _parallel_stoppen(s, sid, aid, nach=0.3):
    ergebnis = {}

    def stopp():
        time.sleep(nach)
        ergebnis["r"] = s.post(f"/api/session/{sid}/stopp", json={"anfrage_id": aid}).json()["ergebnis"]
    th = threading.Thread(target=stopp)
    th.start()
    return th, ergebnis


def _profil(sid):
    return TestClient(app).get(f"/api/teacher/sessions/{sid}").json()["session"]["profile"]


def _events(sid):
    return TestClient(app).get(f"/api/teacher/sessions/{sid}").json()["events"]


def test_antwort_stoppen_zaehlt_nicht(monkeypatch):
    s, sid = _sequenz("Stopp-Antwort")
    vorher = {"profile": _profil(sid)}
    monkeypatch.setenv("ITS_MOCK_DELAY", "5")
    aid = "stopp-antwort-0001"
    th, erg = _parallel_stoppen(s, sid, aid)
    t0 = time.time()
    r = s.post(f"/api/session/{sid}/answer", headers={"X-ITS-Anfrage": aid},
               json={"answer": "Eine ausführliche Antwort, die zu früh abgeschickt wurde.", "confidence": 7})
    th.join()
    assert time.time() - t0 < 3, "der Stopp wirkt sofort, nicht erst nach der Verzögerung"
    assert erg["r"] == "abgebrochen" and r.status_code == 409 and r.json()["detail"]["abgebrochen"] is True
    nachher = {"profile": _profil(sid)}
    assert nachher["profile"]["correct"] == vorher["profile"]["correct"]
    assert nachher["profile"]["wrong"] == vorher["profile"]["wrong"]
    assert nachher["profile"].get("attempts_current", 0) == vorher["profile"].get("attempts_current", 0)
    assert nachher["profile"].get("confidence", []) == vorher["profile"].get("confidence", [])
    typen = [e["type"] for e in _events(sid)]
    assert typen[-1] == "anfrage_abgebrochen" and "answer_evaluated" not in typen
    ab = _events(sid)[-1]["payload"]
    assert ab["art"] == "antwort" and ab["text"].startswith("Eine ausführliche")
    # Danach normal weiter: dieselbe Antwort wird bewertet
    monkeypatch.setenv("ITS_MOCK_DELAY", "0")
    r = s.post(f"/api/session/{sid}/answer", json={"answer": "Eine ausführliche Antwort, die zu früh abgeschickt wurde.",
                                                   "confidence": 7})
    assert r.status_code == 200 and r.json()["bewertung"] in ("korrekt", "teilweise", "falsch")


def test_chat_stoppen_setzt_eskalation_zurueck(monkeypatch):
    s, sid = _sequenz("Stopp-Chat")
    stand = _profil(sid)
    monkeypatch.setenv("ITS_MOCK_DELAY", "5")
    aid = "stopp-chat-000001"
    th, erg = _parallel_stoppen(s, sid, aid)
    r = s.post(f"/api/session/{sid}/chat", headers={"X-ITS-Anfrage": aid},
               json={"message": "Erklär mir die Theorie", "art": "theorie"})
    th.join()
    assert r.status_code == 409 and erg["r"] == "abgebrochen"
    nachher = _profil(sid)
    assert {k: v for k, v in nachher.items() if k != "erklaert"} == {k: v for k, v in stand.items() if k != "erklaert"}
    ev = _events(sid)
    assert ev[-1]["type"] == "anfrage_abgebrochen" and ev[-1]["payload"]["art"] == "theorie"
    assert not any(e["type"] == "chat_reply" for e in ev[-3:])
    # Fortsetzen zeigt den Stopp als Notiz
    verlauf = s.post(f"/api/session/{sid}/fortsetzen").json()["verlauf"]
    assert verlauf[-1] == {"art": "notiz", "zeit": verlauf[-1]["zeit"], "text": "Bearbeitung gestoppt, nicht bewertet."}


def test_stopp_zu_spaet_aendert_nichts():
    s, sid = _sequenz("Stopp-Spaet")
    aid = "stopp-spaet-00001"
    r = s.post(f"/api/session/{sid}/chat", headers={"X-ITS-Anfrage": aid}, json={"message": "Was heisst Haftung?"})
    assert r.status_code == 200
    assert s.post(f"/api/session/{sid}/stopp", json={"anfrage_id": aid}).json()["ergebnis"] == "zu_spaet"
    assert _events(sid)[-1]["type"] == "chat_reply"


def test_stopp_vor_dem_start_und_fremde_sequenz():
    s, sid = _sequenz("Stopp-Vorab")
    aid = "stopp-vorab-00001"
    assert s.post(f"/api/session/{sid}/stopp", json={"anfrage_id": aid}).json()["ergebnis"] == "abgebrochen"
    r = s.post(f"/api/session/{sid}/chat", headers={"X-ITS-Anfrage": aid}, json={"message": "Frage"})
    assert r.status_code == 409
    andere, sid2 = _sequenz("Stopp-Fremd")
    assert andere.post(f"/api/session/{sid}/stopp", json={"anfrage_id": "x" * 12}).status_code == 403
    assert s.post(f"/api/session/{sid}/stopp", json={"anfrage_id": "kurz"}).json()["ergebnis"] == "unbekannt"


def test_ohne_anfrage_id_wie_bisher():
    s, sid = _sequenz("Stopp-Ohne")
    assert s.post(f"/api/session/{sid}/chat", json={"message": "Was heisst Haftung?"}).status_code == 200


def test_einwand_und_einstufung_stoppbar(monkeypatch):
    s = TestClient(app)
    s.post("/api/learner/login", json={"name": "Stopp-Einstufung"})
    sid = s.post("/api/session/start", json={"lesson_id": "haftungsrecht", "neu_beginnen": True}).json()["session_id"]
    monkeypatch.setenv("ITS_MOCK_DELAY", "5")
    aid = "stopp-einstufung1"
    th, erg = _parallel_stoppen(s, sid, aid)
    r = s.post(f"/api/session/{sid}/assess", headers={"X-ITS-Anfrage": aid}, json={"answers": ["a", "b", "c"]})
    th.join()
    assert r.status_code == 409
    st = TestClient(app).get(f"/api/teacher/sessions/{sid}").json()["session"]
    assert st["phase"] == "assessment"
    monkeypatch.setenv("ITS_MOCK_DELAY", "0")
    assert s.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]}).status_code == 200


def test_ollama_wird_beim_stopp_gestreamt_und_geschlossen(monkeypatch):
    """Mit Anfrage-ID streamt der Aufruf; ein Stopp beendet ihn zwischen zwei Teilen."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    abbruch.zuruecksetzen()
    teile = [json.dumps({"message": {"content": "{\"a\": "}, "done": False}),
             json.dumps({"message": {"content": "1}"}, "done": False}),
             json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop",
                         "prompt_eval_count": 10, "eval_count": 3})]
    gesendet = []

    def handler(request):
        gesendet.append(json.loads(request.content))
        return httpx.Response(200, content="\n".join(teile).encode())
    transport = httpx.MockTransport(handler)
    echt = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kw: echt(transport=transport, **kw))
    abbruch.beginnen("ollama-stream-01", "sid-x", "frage", "t")
    text, meta = llm._chat_ollama("sys", "AUFGABE: X\nhallo", json_mode=True)
    assert text == '{"a": 1}' and gesendet[0]["stream"] is True and meta["done_reason"] == "stop"
    abbruch.stoppen("sid-x", "ollama-stream-01")
    with pytest.raises(abbruch.Abgebrochen):
        llm._chat_ollama("sys", "AUFGABE: X\nhallo", json_mode=True)
    with pytest.raises(abbruch.Abgebrochen):
        llm.chat_json("sys", "AUFGABE: X\nhallo", fallback={})          # kein zweiter Versuch, kein Fallback
    abbruch.zuruecksetzen()


def test_ohne_stoppbare_anfrage_kein_streaming(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    abbruch.zuruecksetzen()
    gesehen = []

    def post(url, json=None, timeout=None):
        gesehen.append(json)
        return httpx.Response(200, json={"message": {"content": "{}"}, "done_reason": "stop"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(llm.httpx, "post", post)
    llm._chat_ollama("sys", "AUFGABE: X", json_mode=True)
    assert gesehen[0]["stream"] is False
