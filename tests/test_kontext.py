"""T-08: Zu lange Prompts erkennen und protokollieren."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import llm, tutor
from app.main import app

client = TestClient(app)

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
GROSS = dict(LESSON, id="gross", material=LESSON["material"] * 40)     # rund 115'000 Zeichen


@pytest.fixture(autouse=True)
def aufraeumen():
    """Angelegte Lektionen archivieren, damit die Standardlektion anderer Tests gleich bleibt."""
    vorher = {l["id"] for l in client.get("/api/lessons").json()}
    yield
    for l in client.get("/api/lessons").json():
        if l["id"] not in vorher:
            client.delete(f"/api/teacher/lessons/{l['id']}")


@pytest.fixture
def ollama(monkeypatch):
    """Ollama als Provider, aber ohne Netz: Der Fake liefert unbrauchbaren Text."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "4096")
    calls = []

    def fake(system, user, json_mode=False):
        calls.append(user)
        return "武汉市的天气如何？", {"prompt_tokens": 4096, "antwort_tokens": 12}
    monkeypatch.setitem(llm._PROVIDERS, "ollama", fake)
    return calls


def test_schaetzung_ist_vorsichtig():
    # 3 Zeichen pro Token: deutscher Text wird eher über- als unterschätzt
    assert llm.schaetze_tokens("x" * 3000) == 1001
    assert llm.prompt_tokens_schaetzen("a" * 300, "b" * 300) > 200


def test_ak1_warnung_mit_laenge_maximum_und_differenz(ollama, caplog):
    llm.lektion_setzen("haftungsrecht-v2")
    with caplog.at_level(logging.WARNING, logger="its.llm"):
        tutor.evaluate_answer(GROSS, tutor.new_profile(), {"frage": "Wer haftet?"}, "Anna")
    meldungen = [r.getMessage() for r in caplog.records if "Prompt zu lang" in r.getMessage()]
    assert meldungen, "keine Warnung im Log"
    m = meldungen[0]
    assert "ANTWORT_BEWERTEN" in m and "Lektion haftungsrecht-v2" in m
    assert "Maximum OLLAMA_NUM_CTX=4096" in m and "Überschreitung ca." in m
    import re
    laenge = int(re.search(r": ca\. (\d+) Tokens", m).group(1))
    assert laenge >= llm.schaetze_tokens(tutor._system_prompt(GROSS))   # Länge des ganzen Prompts
    assert f"Überschreitung ca. {laenge - 4096} Tokens" in m


def test_ak1_fallback_traegt_die_drei_werte(ollama):
    data = tutor.generate_theory(GROSS, tutor.new_profile(), [])
    assert data["_fallback"]
    k = data["_kontext"]
    assert k["max_tokens"] == 4096 and k["prompt_tokens"] > 4096
    assert k["differenz"] == k["prompt_tokens"] - 4096 and k["geschaetzt"] is True
    assert "Kontext zu gross" in data["_fehler"]


def test_ak2_lernverlauf_zeigt_kontext_im_fallback_event(ollama):
    r = client.post("/api/teacher/lessons", json={
        "titel": "Haftung gross", "lernziele": ["Haftung erklären"], "material": GROSS["material"]})
    lid = r.json()["id"]
    s = client.post("/api/session/start", json={"name": "Kontext-Test", "lesson_id": lid}).json()
    sid = s["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    client.post(f"/api/session/{sid}/next")
    events = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    fb = [e["payload"] for e in events if e["type"] == "fallback_used"
          and e["payload"]["schrittart"] == "THEORIE_SCHRITT"]
    assert fb and fb[0]["kontext"]["max_tokens"] == 4096
    assert fb[0]["kontext"]["prompt_tokens"] > 4096
    assert "Kontext zu gross" in fb[0]["grund"]


@pytest.mark.parametrize("provider", ["mock", "openai", "anthropic"])
def test_ak3_keine_warnung_bei_anderen_providern(provider, monkeypatch, caplog):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("OLLAMA_NUM_CTX", "100")
    monkeypatch.setitem(llm._PROVIDERS, provider, lambda s, u, json_mode=False: ('{"antwort": "ok"}', {}))
    with caplog.at_level(logging.WARNING, logger="its.llm"):
        data = llm.chat_json("x" * 50000, "AUFGABE: FRAGE_BEANTWORTEN\n", fallback={})
    assert not any("Prompt zu lang" in r.getMessage() for r in caplog.records)
    assert "_kontext" not in data and llm.kontextfenster() is None


def test_nachkontrolle_prompt_eval_count_am_maximum(monkeypatch, caplog):
    """Kurzer Prompt nach Schätzung, aber Ollama meldet volle Auslastung: gilt als gekürzt."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "2048")
    monkeypatch.setitem(llm._PROVIDERS, "ollama",
                        lambda s, u, json_mode=False: ("kein json", {"prompt_tokens": 2048}))
    with caplog.at_level(logging.WARNING, logger="its.llm"):
        data = llm.chat_json("kurz", "AUFGABE: ABSCHLUSS\n", fallback={"x": 1})
    assert data["_kontext"]["geschaetzt"] is False and data["_kontext"]["prompt_tokens"] == 2048
    assert any("prompt_eval_count am Maximum" in r.getMessage() for r in caplog.records)


def test_ak4_editor_warnt_speichert_aber(ollama):
    r = client.post("/api/teacher/lessons", json={
        "titel": "Zu gross", "lernziele": ["Ziel"], "material": GROSS["material"]})
    assert r.status_code == 200
    k = r.json()["kontext"]
    assert k["warnung"] is True and k["max"] == 4096 and "Kontextfenster" in k["text"]
    lid = r.json()["id"]
    assert lid in [l["id"] for l in client.get("/api/lessons").json()]
    liste = {l["id"]: l for l in client.get("/api/teacher/lessons").json()}
    assert liste[lid]["kontext"]["warnung"] is True
    # Kleine Lektion: keine Warnung
    klein = liste["haftungsrecht"]["kontext"]
    assert klein["warnung"] is False and klein["tokens"] < 4096 * 0.8


def test_ak4_ohne_ollama_keine_warnung():
    r = client.post("/api/teacher/lessons", json={
        "titel": "Gross ohne Ollama", "lernziele": ["Ziel"], "material": GROSS["material"]})
    k = r.json()["kontext"]
    assert k["max"] is None and k["warnung"] is False and k["tokens"] > 30000


def test_messuebersicht_zeigt_groessten_prompt():
    llm.reset_timings()
    tutor.generate_theory(LESSON, tutor.new_profile(), [])
    z = {r["schritt"]: r for r in llm.timing_summary()}
    assert z["THEORIE_SCHRITT"]["max_prompt_tokens_geschaetzt"] > 1000
    info = client.get("/api/teacher/timings").json()
    assert "kontextfenster" in info
