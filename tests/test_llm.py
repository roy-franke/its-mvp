"""Tests für die Aufbereitung von LLM-Antworten."""

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
