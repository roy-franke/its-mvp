"""Tests für die Aufbereitung von LLM-Antworten."""

from app import llm
from app.llm import extract_json, ollama_payload, strip_reasoning


def test_gedankenblock_wird_entfernt():
    text = "<think>Ich überlege: {a: 1} könnte passen.</think>\nDie Antwort lautet 42."
    assert strip_reasoning(text) == "Die Antwort lautet 42."


def test_gedankenblock_mit_json_danach():
    text = '<think>Erst prüfen {x}</think>\n{"bewertung": "korrekt"}'
    assert extract_json(strip_reasoning(text)) == {"bewertung": "korrekt"}


def test_abgeschnittener_offener_block():
    text = "Ich denke nach ...</think>\nErgebnis: gut"
    assert strip_reasoning(text) == "Ergebnis: gut"


def test_text_ohne_block_bleibt_unveraendert():
    assert strip_reasoning("Einfach eine Antwort.") == "Einfach eine Antwort."


def test_nur_gedanken_faellt_auf_rohtext_zurueck():
    # Lieber der Rohtext als eine leere Antwort
    assert strip_reasoning("<think>nur Gedanken</think>") == "<think>nur Gedanken</think>"


# ---------------------------------------------------------------- Ollama-Anfrage

def test_denkmodus_standardmaessig_aus(monkeypatch):
    monkeypatch.delenv("OLLAMA_THINK", raising=False)
    assert ollama_payload("sys", "user")["think"] is False


def test_denkmodus_einschaltbar(monkeypatch):
    monkeypatch.setenv("OLLAMA_THINK", "true")
    assert ollama_payload("sys", "user")["think"] is True


def test_denkmodus_leer_laesst_feld_weg(monkeypatch):
    monkeypatch.setenv("OLLAMA_THINK", "")
    assert "think" not in ollama_payload("sys", "user")


def test_kontextfenster_und_keep_alive(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    p = ollama_payload("sys", "user")
    assert p["options"]["num_ctx"] == 8192
    assert p["keep_alive"] == "10m"
    assert p["messages"][0] == {"role": "system", "content": "sys"}


# ---------------------------------------------------------------- Zeitmessung

def test_num_predict_begrenzt_antwortlaenge(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "256")
    assert ollama_payload("sys", "user")["options"]["num_predict"] == 256


def test_schrittart_wird_aus_dem_prompt_gelesen():
    assert llm._label("AUFGABE: ANTWORT_BEWERTEN\nAntwort: ...") == "ANTWORT_BEWERTEN"
    assert llm._label("Antworte mit OK") == "SONSTIGES"


def test_aufrufe_werden_gemessen():
    llm.reset_timings()
    llm.chat("sys", "AUFGABE: NAECHSTE_AUFGABE\nErzeuge Schritt 1")
    llm.chat("sys", "AUFGABE: ANTWORT_BEWERTEN\nAntwort des Lernenden: ausführlich genug")
    eintraege = llm.timings()
    assert [e["schritt"] for e in eintraege] == ["NAECHSTE_AUFGABE", "ANTWORT_BEWERTEN"]
    assert all(e["sekunden"] >= 0 for e in eintraege)


def test_zusammenfassung_gruppiert_nach_schrittart():
    llm.reset_timings()
    llm.record_timing("THEORIE_SCHRITT", 10.0)
    llm.record_timing("THEORIE_SCHRITT", 20.0)
    llm.record_timing("ANTWORT_BEWERTEN", 4.0)
    z = {r["schritt"]: r for r in llm.timing_summary()}
    assert z["THEORIE_SCHRITT"]["anzahl"] == 2
    assert z["THEORIE_SCHRITT"]["median_sekunden"] == 15.0
    assert z["THEORIE_SCHRITT"]["max_sekunden"] == 20.0
    # Der langsamste Schritt steht zuoberst
    assert llm.timing_summary()[0]["schritt"] == "THEORIE_SCHRITT"


def test_ollama_kennzahlen_werden_uebersetzt():
    meta = llm._ollama_meta({
        "prompt_eval_count": 3200, "prompt_eval_duration": 4_000_000_000,
        "eval_count": 400, "eval_duration": 10_000_000_000,
    })
    assert meta["prompt_sekunden"] == 4.0
    assert meta["antwort_sekunden"] == 10.0
    assert meta["tokens_pro_sekunde"] == 40.0
