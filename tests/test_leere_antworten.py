"""T-09: Leere Modellantworten erkennen, anders wiederholen und protokollieren."""

import json

import pytest
from fastapi.testclient import TestClient

from app import llm, tutor
from app.main import app

client = TestClient(app)
LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())


@pytest.fixture
def provider(monkeypatch):
    def _set(p):
        monkeypatch.setitem(llm._PROVIDERS, "mock", p)
        return p
    return _set


def test_ak2_zweiter_versuch_ist_veraendert(provider):
    aufrufe = []

    def p(system, user, json_mode=False):
        aufrufe.append((user, json_mode))
        if llm.LEER_HINWEIS not in user:
            return "", {"done_reason": "length", "antwort_tokens": 1024}
        return '{"antwort": "Jetzt klappt es."}', {}
    provider(p)
    data = llm.chat_json("sys", "AUFGABE: FRAGE_BEANTWORTEN\nx", fallback={"antwort": "fb"})
    assert data["antwort"] == "Jetzt klappt es."
    # format=json bleibt: ohne JSON-Modus schrieb qwen3:30b in der Diagnose bis zum Limit
    assert aufrufe[0][1] is True and aufrufe[1][1] is True
    assert aufrufe[0][0] != aufrufe[1][0] and llm.LEER_HINWEIS in aufrufe[1][0]
    assert "leere Antwort" in data["_fehler_vorher"][0]


def test_leere_antwort_ist_eigener_grund_mit_metadaten(provider):
    provider(lambda s, u, json_mode=False: ("  \n ", {"done_reason": "length", "prompt_tokens": 900,
                                                       "antwort_tokens": 1024, "gesamt_sekunden": 12.0}))
    data = llm.chat_json("sys", "AUFGABE: NAECHSTE_AUFGABE\n", fallback={})
    assert data["_fallback"] and data["_fehlerart"] == "leere_antwort"
    assert data["_antwort_meta"]["done_reason"] == "length"
    assert data["_antwort_meta"]["antwort_tokens"] == 1024
    assert "leere Antwort (done_reason=length, Prompt 900 Tokens, Antwort 1024 Tokens" in data["_fehler"]


def test_unlesbares_json_bleibt_unterscheidbar(provider):
    provider(lambda s, u, json_mode=False: ("kein json", {"done_reason": "stop"}))
    data = llm.chat_json("sys", "AUFGABE: NAECHSTE_AUFGABE\n", fallback={})
    assert data["_fehlerart"] == "json_unlesbar"
    assert "kein lesbares JSON" in data["_fehler"]


def test_mock_leer_json_gelingt_im_zweiten_versuch(monkeypatch):
    monkeypatch.setenv("ITS_MOCK_FAIL", "THEORIE_SCHRITT:leer_json")
    data = tutor.generate_theory(LESSON, tutor.new_profile(), [])
    assert not data.get("_fallback") and data["typ"] == "theorie"
    assert data["_versuche"] == 2


def test_ak3_lernverlauf_zeigt_leere_antwort_als_grund(monkeypatch):
    r = client.post("/api/session/start", json={"name": "Leer-Test"}).json()
    sid = r["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    monkeypatch.setenv("ITS_MOCK_FAIL", "THEORIE_SCHRITT:leer")
    client.post(f"/api/session/{sid}/next")
    events = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    fb = [e["payload"] for e in events if e["type"] == "fallback_used"]
    assert fb and fb[-1]["art"] == "leere_antwort"
    assert fb[-1]["antwort_meta"] == {"done_reason": "length", "prompt_tokens": 1200,
                                      "antwort_tokens": 1024, "gesamt_sekunden": 9.5}


def test_antwort_im_feld_thinking_wird_verwendet(monkeypatch):
    """Qwen3 beginnt trotz think=false mit <think>: Ollama legt alles ins Feld thinking."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "", "thinking": 'Okay ... {"antwort": "aus thinking"}'},
                    "done_reason": "stop", "prompt_eval_count": 50, "eval_count": 30}
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: R())
    data = llm.chat_json("sys", "AUFGABE: FRAGE_BEANTWORTEN\n", fallback={})
    assert data["antwort"] == "aus thinking"


def test_ollama_meta_enthaelt_done_reason():
    m = llm._ollama_meta({"done_reason": "length", "eval_count": 1024, "total_duration": 9_500_000_000,
                          "message": {"thinking": "abc"}})
    assert m["done_reason"] == "length" and m["gesamt_sekunden"] == 9.5 and m["thinking_zeichen"] == 3


class _Antwort:
    def __init__(self, daten, status=200):
        self.daten, self.status_code, self.text = daten, status, ""

    def raise_for_status(self):
        pass

    def json(self):
        return self.daten


def test_denkmodus_ohne_think_feld_wird_mit_think_false_wiederholt(monkeypatch):
    """Diagnose 12.10.2026, Variante D: ohne Feld think denkt qwen3:30b bis zum Limit."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_THINK", "")                      # Feld think fehlt
    gesendet = []

    def post(url, json=None, timeout=None):
        gesendet.append(dict(json))
        if json.get("think") is False:
            return _Antwort({"message": {"content": '{"antwort": "direkt"}'}, "done_reason": "stop"})
        return _Antwort({"message": {"content": "", "thinking": "Okay, let me think " * 200},
                         "done_reason": "length", "eval_count": 1024})
    monkeypatch.setattr(llm.httpx, "post", post)
    data = llm.chat_json("sys", "AUFGABE: FRAGE_BEANTWORTEN\n", fallback={})
    assert data["antwort"] == "direkt" and data["_versuche"] == 1
    assert "think" not in gesendet[0] and gesendet[1]["think"] is False


def test_think_false_ohne_inhalt_wird_nicht_endlos_wiederholt(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_THINK", "false")
    gesendet = []

    def post(url, json=None, timeout=None):
        gesendet.append(json)
        return _Antwort({"message": {"content": "", "thinking": "hmm"}, "done_reason": "length"})
    monkeypatch.setattr(llm.httpx, "post", post)
    data = llm.chat_json("sys", "AUFGABE: FRAGE_BEANTWORTEN\n", fallback={})
    assert data["_fallback"] and data["_fehlerart"] == "leere_antwort"
    assert len(gesendet) == 2                                    # zwei Versuche, keine Zusatzaufrufe
