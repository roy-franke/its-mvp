"""LLM-Abstraktionsschicht.

Ein Provider-Interface, mehrere Implementierungen:
- anthropic: Claude via Anthropic API (Cloud)
- openai:    OpenAI oder jede OpenAI-kompatible API (Cloud)
- ollama:    Lokales LLM via Ollama (On-Premise, z.B. RIB-AI-01)
- mock:      Deterministische Antworten ohne LLM (Entwicklung/Demo)

Der Provider wird via .env gewählt (LLM_PROVIDER). Alle Provider liefern
Text; die Tutorlogik verlangt JSON und parst robust mit Fallbacks.
"""

import json
import logging
import os
import re

import httpx

log = logging.getLogger("its.llm")

# Grosse lokale Modelle brauchen beim ersten Aufruf Zeit zum Laden.
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))


class LLMError(Exception):
    pass


# ---------------------------------------------------------------- Provider

def _chat_anthropic(system: str, user: str) -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY fehlt in .env")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _chat_openai(system: str, user: str) -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise LLMError("OPENAI_API_KEY fehlt in .env")
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    r = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _chat_ollama(system: str, user: str) -> str:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    # Ollamas Standardkontext (4096 Token) reicht für Lektionsmaterial plus
    # Lernverlauf nicht aus; zu viel wird sonst still abgeschnitten.
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    r = httpx.post(
        f"{base}/api/chat",
        json={
            "model": model,
            "stream": False,
            "options": {"num_ctx": num_ctx},
            # Modell im Speicher halten, damit es zwischen zwei Aufgaben
            # nicht neu geladen werden muss (Wartezeit im Unterricht).
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _chat_mock(system: str, user: str) -> str:
    """Deterministischer Fake-Provider für Entwicklung und Demos ohne LLM."""
    if "EINSTUFUNGSFRAGEN" in user:
        return json.dumps({
            "questions": [
                "Was verstehst du unter Haftpflicht? Beschreibe es in eigenen Worten.",
                "Ein Velofahrer beschädigt ein parkiertes Auto. Wer haftet und warum?",
                "Kennst du den Unterschied zwischen Verschuldenshaftung und Kausalhaftung?",
            ]
        }, ensure_ascii=False)
    if "EINSTUFUNG_BEWERTEN" in user:
        return json.dumps({
            "level": "intermediate",
            "begruendung": "Grundbegriffe sind bekannt, Details zur Kausalhaftung fehlen noch.",
        }, ensure_ascii=False)
    if "THEORIE_SCHRITT" in user:
        return json.dumps({
            "titel": "Grundprinzip der Verschuldenshaftung",
            "inhalt": "Wer einem anderen widerrechtlich Schaden zufügt, muss ihn ersetzen (Art. 41 OR). Damit jemand haftet, braucht es vier Voraussetzungen: einen Schaden, Widerrechtlichkeit, einen Kausalzusammenhang und ein Verschulden. Beispiel: Du spielst im Hof Fussball und schiesst eine Fensterscheibe ein. Der Schaden ist die kaputte Scheibe, widerrechtlich ist die Verletzung fremden Eigentums, dein Schuss ist die Ursache, und fahrlässig gehandelt hast du auch. Also haftest du. (Mock-Theorie – für echten Lerninhalt LLM-Provider konfigurieren.)",
            "konzept": "Verschuldenshaftung",
        }, ensure_ascii=False)
    if "NAECHSTE_AUFGABE" in user:
        return json.dumps({
            "titel": "Fallbeispiel Alltagshaftung",
            "inhalt": "Anna leiht sich das Snowboard ihrer Freundin und beschädigt es beim Sturz. Muss Anna den Schaden bezahlen?",
            "frage": "Begründe deine Antwort mit dem Grundprinzip der Verschuldenshaftung (Art. 41 OR).",
            "konzept": "Verschuldenshaftung",
        }, ensure_ascii=False)
    if "ANTWORT_BEWERTEN" in user:
        # Heuristik statt fester Antwort, damit die Adaption auch ohne LLM
        # sichtbar wird: lange Antworten korrekt, mittlere teilweise, kurze falsch.
        m = re.search(r"Antwort des Lernenden:\s*(.+)", user)
        ans = (m.group(1).strip() if m else "")
        if len(ans) >= 40:
            return json.dumps({
                "bewertung": "korrekt",
                "feedback": "Richtig: Es braucht Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
                "hinweis": "",
            }, ensure_ascii=False)
        if len(ans) >= 15:
            return json.dumps({
                "bewertung": "teilweise",
                "feedback": "Der Ansatz stimmt, aber es fehlen wesentliche Voraussetzungen der Haftung. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
                "hinweis": "Welche vier Voraussetzungen verlangt Art. 41 OR?",
            }, ensure_ascii=False)
        return json.dumps({
            "bewertung": "falsch",
            "feedback": "Das ist noch zu knapp. Nenne die vier Voraussetzungen der Verschuldenshaftung und wende sie auf den Fall an. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
            "hinweis": "Denk an Art. 41 OR: Schaden, Widerrechtlichkeit, Kausalzusammenhang, Verschulden.",
        }, ensure_ascii=False)
    if "FRAGE_BEANTWORTEN" in user:
        return json.dumps({
            "antwort": "Gute Frage! Die Verschuldenshaftung nach Art. 41 OR setzt Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden voraus. Überleg dir, welche dieser Voraussetzungen in der aktuellen Aufgabe zu prüfen sind. (Mock-Antwort – für echtes Tutoring LLM-Provider konfigurieren.)",
        }, ensure_ascii=False)
    if "LERNZIELE_VORSCHLAGEN" in user:
        return json.dumps({
            "titel": "Neue Lektion (Mock-Vorschlag)",
            "lernziele": [
                "Die zentralen Begriffe des Materials erklären",
                "Die wichtigsten Zusammenhänge an Beispielen anwenden",
                "Typische Fälle selbständig einordnen und begründen",
            ],
        }, ensure_ascii=False)
    if "ABSCHLUSS" in user:
        return json.dumps({
            "zusammenfassung": "Du hast die Grundprinzipien der Haftpflicht verstanden und auf Fälle angewendet.",
            "erreichte_lernziele": ["Grundbegriffe der Haftpflicht erklären"],
            "empfehlung": "Vertiefe die Kausalhaftung mit weiteren Fallbeispielen.",
        }, ensure_ascii=False)
    return "{}"


_PROVIDERS = {
    "anthropic": _chat_anthropic,
    "openai": _chat_openai,
    "ollama": _chat_ollama,
    "mock": _chat_mock,
}


def provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "mock").lower().strip()


def current_model() -> str:
    name = provider_name()
    if name == "anthropic":
        return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    if name == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if name == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    return "mock"


def chat(system: str, user: str) -> str:
    """Sendet einen Prompt an den konfigurierten Provider und gibt Text zurück."""
    name = provider_name()
    fn = _PROVIDERS.get(name)
    if fn is None:
        raise LLMError(f"Unbekannter LLM_PROVIDER: {name}")
    log.info("LLM-Request an Provider=%s", name)
    log.debug("SYSTEM: %s\nUSER: %s", system, user)
    text = fn(system, user)
    log.debug("ANTWORT: %s", text)
    return strip_reasoning(text)


def strip_reasoning(text: str) -> str:
    """Entfernt Gedankenblöcke von Reasoning-Modellen (z.B. Qwen3, DeepSeek-R1).

    Diese Modelle stellen ihrer Antwort <think>…</think> voran. Der Block darf
    weder im JSON-Parsing landen noch als Tutortext bei Lernenden erscheinen.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Abgeschnittene Antwort mit offenem Block: alles bis zum Tag verwerfen
    cleaned = re.sub(r"^.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip() or text.strip()


# ---------------------------------------------------------------- JSON-Parsing

def chat_json(system: str, user: str, fallback: dict) -> dict:
    """Wie chat(), erwartet aber JSON. Parst robust, liefert fallback bei Fehlern."""
    try:
        text = chat(system, user)
    except Exception as e:
        log.error("LLM-Fehler: %s", e)
        out = dict(fallback)
        out["_llm_error"] = str(e)
        return out
    parsed = extract_json(text)
    if parsed is None:
        log.warning("Konnte kein JSON aus LLM-Antwort extrahieren: %.200s", text)
        out = dict(fallback)
        out["_raw"] = text[:500]
        return out
    return parsed


def extract_json(text: str):
    """Extrahiert das erste JSON-Objekt aus einem Text (auch in ```-Blöcken)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
