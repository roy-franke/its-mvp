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
import contextvars
import os
import re
import statistics
import time
from collections import deque

import httpx

from . import didaktik

log = logging.getLogger("its.llm")

# Grosse lokale Modelle brauchen beim ersten Aufruf Zeit zum Laden.
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))


class LLMError(Exception):
    pass


# ---------------------------------------------------------------- Zeitmessung
#
# Ohne Zahlen ist jede Optimierung Raten. Jeder LLM-Aufruf landet deshalb in
# einem Ringpuffer im Arbeitsspeicher: Dauer, Art des Schritts und – bei
# Ollama – die Aufteilung in Prompt-Verarbeitung und Textgenerierung. Das
# genügt für die Frage «wo gehen die Sekunden hin», ohne dass dafür eine
# Tabelle in der Datenbank nötig wäre.

_TIMINGS: deque = deque(maxlen=200)
# Fallbacks separat zählen: Ein Fallback ist kein einzelner Aufruf, sondern das
# Ergebnis mehrerer gescheiterter Versuche (T-01).
_FALLBACKS: deque = deque(maxlen=200)


def _label(user: str) -> str:
    """Liest die Schrittart aus der ersten Zeile des Prompts ("AUFGABE: X")."""
    m = re.match(r"\s*AUFGABE:\s*([A-Z_]+)", user)
    return m.group(1) if m else "SONSTIGES"


def record_timing(label: str, seconds: float, meta: dict | None = None) -> None:
    entry = {"schritt": label, "sekunden": round(seconds, 2),
             "zeitpunkt": time.time(), "modell": current_model()}
    entry.update(meta or {})
    _TIMINGS.append(entry)
    log.info("LLM %s: %.1fs (%s)", label, seconds,
             ", ".join(f"{k}={v}" for k, v in (meta or {}).items()) or "keine Details")


def timings() -> list[dict]:
    return list(_TIMINGS)


def record_fallback(label: str, grund: str, kontext: dict | None = None) -> None:
    eintrag = {"schritt": label, "grund": grund[:300], "zeitpunkt": time.time()}
    if kontext:
        eintrag["kontext"] = kontext
    _FALLBACKS.append(eintrag)
    log.warning("FALLBACK %s: %s", label, grund)


def fallbacks() -> list[dict]:
    return list(_FALLBACKS)


def _mark_last_error(label: str, grund: str) -> None:
    """Hängt einen Fehlergrund an die letzte Messung dieser Schrittart."""
    for e in reversed(_TIMINGS):
        if e["schritt"] == label:
            e.setdefault("fehler", grund[:200])
            return


def timing_summary() -> list[dict]:
    """Aggregiert die Messungen je Schrittart – Median und langsamster Fall."""
    by_label: dict[str, list[float]] = {}
    fehler: dict[str, int] = {}
    prompt_max: dict[str, int] = {}          # T-08: grösste gemessene Promptlänge
    prompt_max_geschaetzt: dict[str, int] = {}
    for e in _TIMINGS:
        by_label.setdefault(e["schritt"], []).append(e["sekunden"])
        if e.get("fehler"):
            fehler[e["schritt"]] = fehler.get(e["schritt"], 0) + 1
        if isinstance(e.get("prompt_tokens"), int):
            prompt_max[e["schritt"]] = max(prompt_max.get(e["schritt"], 0), e["prompt_tokens"])
        if isinstance(e.get("prompt_tokens_geschaetzt"), int):
            prompt_max_geschaetzt[e["schritt"]] = max(prompt_max_geschaetzt.get(e["schritt"], 0),
                                                      e["prompt_tokens_geschaetzt"])
    fb: dict[str, int] = {}
    for f in _FALLBACKS:
        fb[f["schritt"]] = fb.get(f["schritt"], 0) + 1
        by_label.setdefault(f["schritt"], [])
    out = []
    for label, werte in by_label.items():
        out.append({
            "schritt": label,
            "anzahl": len(werte),
            "median_sekunden": round(statistics.median(werte), 1) if werte else 0.0,
            "max_sekunden": round(max(werte), 1) if werte else 0.0,
            "fehler": fehler.get(label, 0),
            "fallbacks": fb.get(label, 0),
            "max_prompt_tokens": prompt_max.get(label),
            "max_prompt_tokens_geschaetzt": prompt_max_geschaetzt.get(label),
        })
    return sorted(out, key=lambda r: r["median_sekunden"], reverse=True)


def reset_timings() -> None:
    _TIMINGS.clear()
    _FALLBACKS.clear()


# ---------------------------------------------------------------- Kontextfenster (T-08)
#
# Ollama kürzt einen Prompt, der länger als OLLAMA_NUM_CTX ist, stillschweigend
# und warnt nur im eigenen Log («truncating input prompt»). Der ITS-Service
# schätzt deshalb vor jedem Aufruf die Länge und schreibt eine Warnung, wenn
# der Prompt nicht ins Kontextfenster passt. Abgebrochen oder gekürzt wird
# nichts (Entscheid E8).
#
# Schätzung ohne Tokenizer: Zeichenzahl geteilt durch einen bewusst
# vorsichtigen Faktor. Deutscher Text braucht bei Qwen- und Llama-Tokenizern
# erfahrungsgemäss etwa 3,5 bis 4,5 Zeichen pro Token; mit 3,0 wird die Länge
# eher über- als unterschätzt. Die Kalibrierung gegen prompt_eval_count ist in
# der Messübersicht sichtbar (geschätzt neben gemessen) und lässt sich mit
# tests/eval/diagnose_ollama.py nachprüfen.

# Kalibriert am 12.10.2026 mit qwen3:30b: Mit 3.0 lag die Schätzung 15 % über
# prompt_eval_count. 3.4 bleibt knapp vorsichtig.
ZEICHEN_PRO_TOKEN = float(os.getenv("ITS_ZEICHEN_PRO_TOKEN", "3.4"))
TOKENS_PRO_NACHRICHT = 8          # Rollen-Markierungen der Chat-Vorlage
KONTEXT_WARNGRENZE = 0.8          # Lektionseditor: Warnung ab 80 Prozent

_lektion: contextvars.ContextVar = contextvars.ContextVar("lektion", default=None)


def lektion_setzen(lesson_id: str | None) -> None:
    """Merkt sich die Lektion des laufenden Requests für Warnungen im Log."""
    _lektion.set(lesson_id)


def schaetze_tokens(text: str) -> int:
    return int(len(text or "") / ZEICHEN_PRO_TOKEN) + 1


def prompt_tokens_schaetzen(system: str, user: str) -> int:
    return schaetze_tokens(system) + schaetze_tokens(user) + 2 * TOKENS_PRO_NACHRICHT


def num_ctx() -> int:
    return int(os.getenv("OLLAMA_NUM_CTX", "16384"))


def kontextfenster() -> int | None:
    """Grösse des Kontextfensters, sofern der Provider eines hat, das wir kennen.

    Nur bei Ollama: Die Cloud-Provider haben sehr grosse Fenster und melden
    eine Überschreitung als Fehler statt still zu kürzen (AK 3).
    """
    return num_ctx() if provider_name() == "ollama" else None


def _kontext_ueberschritten(label: str, tokens: int, geschaetzt: bool) -> dict:
    maximum = num_ctx()
    info = {"prompt_tokens": tokens, "max_tokens": maximum,
            "differenz": tokens - maximum, "geschaetzt": geschaetzt}
    log.warning("Prompt zu lang für das Kontextfenster (%s, Lektion %s): %s%d Tokens, Maximum "
                "OLLAMA_NUM_CTX=%d, Überschreitung %s%d Tokens.%s",
                label, _lektion.get() or "unbekannt", "ca. " if geschaetzt else "", tokens,
                maximum, "ca. " if geschaetzt else "", max(tokens - maximum, 0),
                "" if geschaetzt else " (prompt_eval_count am Maximum, Ollama hat gekürzt)")
    return info


def _ollama_meta(data: dict) -> dict:
    """Übersetzt Ollamas Nanosekunden-Zähler in etwas Lesbares.

    Interessant ist die Aufteilung: Ist die Prompt-Verarbeitung teuer, hilft
    ein kürzeres Lektionsmaterial. Ist die Generierung teuer, hilft nur ein
    schnelleres Modell oder eine kürzere Antwort.
    """
    def sek(key: str) -> float | None:
        v = data.get(key)
        return round(v / 1e9, 2) if isinstance(v, (int, float)) else None

    meta = {
        "prompt_tokens": data.get("prompt_eval_count"),
        "antwort_tokens": data.get("eval_count"),
        "prompt_sekunden": sek("prompt_eval_duration"),
        "antwort_sekunden": sek("eval_duration"),
        "laden_sekunden": sek("load_duration"),
        "gesamt_sekunden": sek("total_duration"),
        # T-09: «stop» = regulär beendet, «length» = an OLLAMA_NUM_PREDICT abgeschnitten
        "done_reason": data.get("done_reason"),
    }
    denken = (data.get("message") or {}).get("thinking")
    if denken:
        meta["thinking_zeichen"] = len(denken)
    tokens, dauer = data.get("eval_count"), meta["antwort_sekunden"]
    if tokens and dauer:
        meta["tokens_pro_sekunde"] = round(tokens / dauer, 1)
    return {k: v for k, v in meta.items() if v is not None}


# ---------------------------------------------------------------- Provider

# Temperatur für den laufenden Aufruf. Die Bewertung läuft mit niedriger
# Temperatur, damit dieselbe Antwort nicht einmal korrekt und einmal falsch
# ist (D-05); Aufgaben und Theorie behalten die Standardtemperatur des Modells,
# damit sie abwechslungsreich bleiben. Das Feld steht in den Optionen, nicht im
# Prompt, und ändert deshalb nichts am Prompt-Cache.
_temperatur: contextvars.ContextVar = contextvars.ContextVar("temperatur", default=None)


def temperatur() -> float | None:
    return _temperatur.get()


def _chat_anthropic(system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
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
            **({"temperature": temperatur()} if temperatur() is not None else {}),
            "messages": [{"role": "user", "content": user}],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    return data["content"][0]["text"], {
        "prompt_tokens": usage.get("input_tokens"),
        "antwort_tokens": usage.get("output_tokens"),
    }


def _chat_openai(system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
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
            **({"temperature": temperatur()} if temperatur() is not None else {}),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    return data["choices"][0]["message"]["content"], {
        "prompt_tokens": usage.get("prompt_tokens"),
        "antwort_tokens": usage.get("completion_tokens"),
    }


def ollama_payload(system: str, user: str, json_mode: bool = False) -> dict:
    """Baut die Anfrage an Ollama zusammen (ausgelagert, damit testbar)."""
    payload = {
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "stream": False,
        # Ollamas Standardkontext (4096 Token) reicht für Lektionsmaterial plus
        # Lernverlauf nicht aus; zu viel wird sonst still abgeschnitten.
        "options": {
            "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "16384")),
            # Obergrenze für die Antwortlänge. Der Tutor braucht selten mehr
            # als 500 Token; die Grenze verhindert nur, dass ein Modell im
            # Ausnahmefall minutenlang weiterschreibt.
            "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "1024")),
        },
        # Modell im Speicher halten, damit es zwischen zwei Aufgaben nicht neu
        # geladen werden muss (Wartezeit im Unterricht).
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # Reasoning-Modelle denken vor jeder Antwort sichtbar nach. Das kostet
    # Sekunden pro Schritt, die Lernende als Wartezeit erleben, und der
    # Gedankengang wird ohnehin verworfen. Standardmässig deshalb aus;
    # OLLAMA_THINK=true schaltet ihn für Qualitätsvergleiche wieder ein,
    # ein leerer Wert überlässt die Entscheidung dem Modell.
    think = os.getenv("OLLAMA_THINK", "false").strip().lower()
    if think in ("true", "false"):
        payload["think"] = think == "true"
    # Wo die Tutorlogik JSON erwartet, erzwingt Ollama mit format=json gültiges
    # JSON. Das verhindert die häufigste Fallback-Ursache (T-01): LaTeX-Befehle
    # wie \Delta oder rohe Zeilenumbrüche in Zeichenketten, an denen das
    # Parsen scheitert. OLLAMA_FORMAT_JSON=false schaltet das ab.
    if json_mode and os.getenv("OLLAMA_FORMAT_JSON", "true").strip().lower() != "false":
        payload["format"] = "json"
    if temperatur() is not None:
        payload["options"]["temperature"] = temperatur()
    return payload


def _chat_ollama(system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    payload = ollama_payload(system, user, json_mode)
    r = httpx.post(f"{base}/api/chat", json=payload, timeout=TIMEOUT)
    if r.status_code == 400 and "think" in payload:
        # Modelle ohne Denkmodus lehnen das Feld ab – ohne erneut versuchen
        log.info("Modell kennt keinen Denkmodus, Anfrage ohne 'think'")
        payload.pop("think")
        r = httpx.post(f"{base}/api/chat", json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    meta = _ollama_meta(data)
    inhalt = data["message"].get("content") or ""
    denken = data["message"].get("thinking") or ""
    if not inhalt.strip() and "{" in denken:
        # T-09: Qwen3 beginnt trotz think=false gelegentlich mit «<think>». Ollama
        # schiebt dann die ganze Ausgabe ins Feld thinking, und content bleibt
        # leer. Steht dort ein JSON-Objekt, wird es verwendet.
        log.warning("Leerer content, Antwort stand im Feld thinking (%d Zeichen)", len(denken))
        meta["aus_thinking"] = True
        inhalt = denken
    return inhalt, meta


def _mock_quelle(user: str) -> dict:
    """N-01: Der Mock nennt die erste angebotene Quelle, mit ITS_MOCK_QUELLE eine
    frei gewählte (für den Test einer erfundenen Quelle)."""
    m = re.search(r"aus der deine Erklärung stammt: (.+?)\.\n", user)
    if not m:
        return {}
    return {"quelle": os.getenv("ITS_MOCK_QUELLE") or m.group(1).split(", ")[0]}


def _mock_text(system: str, user: str) -> str:
    """Deterministischer Fake-Provider für Entwicklung und Demos ohne LLM."""
    if _label(user) == "WITZ":
        return json.dumps({"witz": "Warum hat das Lehrbuch so gute Laune? Es hat einfach für jedes "
                                   "Problem ein Kapitel. (Mock-Witz)"}, ensure_ascii=False)
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
            "inhalt": "Wer einem anderen widerrechtlich Schaden zufügt, muss ihn ersetzen (Art. 41 OR). Damit jemand haftet, braucht es vier Voraussetzungen: einen Schaden, Widerrechtlichkeit, einen Kausalzusammenhang und ein Verschulden. Fehlt eine davon, entfällt die Haftung, weil das Gesetz alle vier verlangt. (Mock-Theorie – für echten Lerninhalt LLM-Provider konfigurieren.)",
            "beispiel": "Du spielst im Hof Fussball und schiesst eine Fensterscheibe ein. Der Schaden ist die kaputte Scheibe, widerrechtlich ist die Verletzung fremden Eigentums, dein Schuss ist die Ursache, und fahrlässig gehandelt hast du auch. Also haftest du.",
            "konzept": "Verschuldenshaftung",
            **_mock_quelle(user),
        }, ensure_ascii=False)
    if "NAECHSTE_AUFGABE" in user:
        return json.dumps({
            "titel": "Fallbeispiel Alltagshaftung",
            "inhalt": "Anna leiht sich das Snowboard ihrer Freundin und beschädigt es beim Sturz. Muss Anna den Schaden bezahlen?",
            "frage": "Begründe deine Antwort mit dem Grundprinzip der Verschuldenshaftung (Art. 41 OR).",
            "aufgabentyp": "anwenden",
            "optionen": [],
            "erwartete_antwort": "Anna muss zahlen, weil sie fahrlässig einen Schaden verursacht hat und alle vier Voraussetzungen erfüllt sind.",
            "schluesselbegriffe": ["fahrlässig", "Widerrechtlichkeit"],
            "erwartete_elemente": ["Entscheid, ob Anna zahlen muss",
                                   "Begründung mit den Voraussetzungen der Verschuldenshaftung"],
            "konzept": "Verschuldenshaftung",
        }, ensure_ascii=False)
    if "ANTWORT_BEWERTEN" in user:
        # Heuristik statt fester Antwort, damit die Adaption auch ohne LLM
        # sichtbar wird: lange Antworten korrekt, mittlere teilweise, kurze falsch.
        m = (re.search(r"Nachbesserung des Lernenden:\s*(.+)", user)
             or re.search(r"Antwort des Lernenden:\s*(.+)", user))
        ans = (m.group(1).strip() if m else "")
        if len(ans) >= 40:
            return json.dumps({
                "elemente": [{"element": "Voraussetzungen genannt", "status": "korrekt"},
                             {"element": "auf den Fall angewendet", "status": "korrekt"}],
                "sachlicher_widerspruch": False,
                "bewertung": "korrekt",
                "feedback": "Richtig: Es braucht Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
                "hinweis": "",
            }, ensure_ascii=False)
        if len(ans) >= 15:
            return json.dumps({
                "elemente": [{"element": "Schaden erkannt", "status": "korrekt"},
                             {"element": "übrige Voraussetzungen", "status": "fehlt"}],
                "sachlicher_widerspruch": False,
                "bewertung": "teilweise",
                "feedback": "Der Ansatz stimmt, aber es fehlen wesentliche Voraussetzungen der Haftung. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
                "hinweis": "Welche vier Voraussetzungen verlangt Art. 41 OR?",
            }, ensure_ascii=False)
        return json.dumps({
            "elemente": [{"element": "Voraussetzungen genannt", "status": "fehlt"},
                         {"element": "auf den Fall angewendet", "status": "fehlt"}],
            "sachlicher_widerspruch": False,
            "bewertung": "falsch",
            "feedback": "Das ist noch zu knapp. Nenne die vier Voraussetzungen der Verschuldenshaftung und wende sie auf den Fall an. (Mock-Bewertung – für echte Beurteilung LLM-Provider konfigurieren.)",
            "hinweis": "Denk an Art. 41 OR: Schaden, Widerrechtlichkeit, Kausalzusammenhang, Verschulden.",
        }, ensure_ascii=False)
    if "FRAGE_BEANTWORTEN" in user:
        if "ALLGEMEINWISSEN:" in user:
            return json.dumps({
                "antwort": "Aus dem Allgemeinwissen: Haftungsregeln verteilen Risiken, damit Geschädigte nicht auf ihren Kosten sitzen bleiben. Deshalb verlangt das Recht Sorgfalt von allen. (Mock-Antwort)",
                "konzept": "", "ausserhalb_material": True,
            }, ensure_ascii=False)
        if "ESKALATIONSSTUFE: 2" in user:
            return json.dumps({
                "antwort": "Stell dir eine Checkliste mit vier Kästchen vor: Erst wenn jedes Kästchen angekreuzt ist, entsteht eine Pflicht zum Ersatz. Schritt 1 fragt nach einer Einbusse, Schritt 2 nach einem verletzten Recht, Schritt 3 nach der Ursache, Schritt 4 nach mangelnder Sorgfalt. (Mock-Antwort)",
                "konzept": "", "ausserhalb_material": False,
            }, ensure_ascii=False)
        if "ESKALATIONSSTUFE: 1" in user:
            return json.dumps({
                "antwort": "Ein anderer Blickwinkel: Wer beim Zügeln die geliehene Lampe des Nachbarn fallen lässt, muss sie ersetzen, weil er unsorgfältig war und dadurch fremdes Eigentum zerstört hat. Genau diese Verbindung aus Unsorgfalt und Folge macht die Pflicht aus. (Mock-Antwort)",
                "konzept": "", "ausserhalb_material": False,
            }, ensure_ascii=False)
        wunsch = re.search(r"Verständnisfrage:\s*(.+)", user)
        frage = (wunsch.group(1) if wunsch else "").lower()
        if "grundniveau" in frage and "bleiben" in frage:
            return json.dumps({"antwort": "Verstanden.", "konzept": "", "ausserhalb_material": False,
                               "niveau_wunsch": "halten", "niveau_ziel": "basic"}, ensure_ascii=False)
        return json.dumps({
            "antwort": "Gute Frage! Die Verschuldenshaftung nach Art. 41 OR setzt Schaden, Widerrechtlichkeit, Kausalzusammenhang und Verschulden voraus. Überleg dir, welche dieser Voraussetzungen in der aktuellen Aufgabe zu prüfen sind. (Mock-Antwort – für echtes Tutoring LLM-Provider konfigurieren.)",
            "konzept": "", "ausserhalb_material": False,
        }, ensure_ascii=False)
    if "MATERIAL_PRUEFEN" in user:
        # Heuristik statt Urteil: Stichworte, Beispiel- und Begründungsmarker
        teil = user.split("LERNZIELE:", 1)[1]
        ziele_txt, material = teil.split("MATERIAL:", 1)
        material = material.rsplit("Format:", 1)[0].lower()
        ergebnisse = []
        for z in re.findall(r"^- (.+)$", ziele_txt, re.MULTILINE):
            woerter = [w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöü]{6,}", z)]
            treffer = [w for w in woerter if w[:6] in material]
            beispiel = bool(re.search(r"beispiel|z\.\s?b\.|etwa wenn", material))
            grund = bool(re.search(r"\b(weil|denn|deshalb|daher|darum)\b", material))
            ergebnisse.append({"ziel": z, "erklaerung": bool(treffer), "beispiel": beispiel,
                               "begruendung": grund,
                               "hinweis": "" if treffer and beispiel and grund else "Mock: Lücke gefunden."})
        return json.dumps({"ziele": ergebnisse, "gesamt": "Mock-Prüfung."}, ensure_ascii=False)
    if "LERNZIELE_VORSCHLAGEN" in user:
        return json.dumps({
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


def _chat_mock(system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
    # Für Oberflächentests: ITS_MOCK_DELAY verzögert jede Antwort (Sekunden),
    # ITS_MOCK_FAIL lässt die genannten Schrittarten scheitern (kommagetrennt).
    delay = float(os.getenv("ITS_MOCK_DELAY", "0") or 0)
    if delay > 0:
        time.sleep(delay)
    # Varianten (T-09): «X:leer» liefert immer eine leere Antwort, «X:leer_json»
    # nur mit format=json, so dass der veränderte zweite Versuch gelingt.
    fail = {x.strip() for x in os.getenv("ITS_MOCK_FAIL", "").split(",") if x.strip()}
    label = _label(user)
    if label in fail:
        raise LLMError(f"Mock-Fehler für {label} (ITS_MOCK_FAIL)")
    leer_meta = {"done_reason": "length", "prompt_tokens": 1200, "antwort_tokens": 1024,
                 "gesamt_sekunden": 9.5}
    if f"{label}:leer" in fail or (f"{label}:leer_json" in fail and json_mode):
        return "\n\n   \n", leer_meta
    return _mock_text(system, user), {}


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


def chat(system: str, user: str, json_mode: bool = False) -> str:
    """Sendet einen Prompt an den konfigurierten Provider und gibt Text zurück.

    Scheitert der Aufruf, landet der Fehlergrund in der Zeitmessung, damit er
    im Lehrpersonen-Monitoring sichtbar wird, und die Ausnahme geht weiter.
    """
    return _chat_mit_info(system, user, json_mode)[0]


class LLMAufrufFehler(LLMError):
    """Gescheiterter Aufruf, der die Angaben zum Kontextfenster mitträgt."""

    def __init__(self, original: Exception, info: dict):
        super().__init__(f"{type(original).__name__}: {original}")
        self.original = original
        self.info = info


def _chat_mit_info(system: str, user: str, json_mode: bool = False) -> tuple[str, dict]:
    """Wie chat(), liefert zusätzlich die Metadaten des Aufrufs.

    info enthält `meta` (Tokenzahlen, bei Ollama auch done_reason) und
    `kontext`, wenn der Prompt das Kontextfenster überschreitet (T-08).
    """
    name = provider_name()
    fn = _PROVIDERS.get(name)
    if fn is None:
        raise LLMError(f"Unbekannter LLM_PROVIDER: {name}")
    log.debug("SYSTEM: %s\nUSER: %s", system, user)
    label = _label(user)
    info: dict = {}
    geschaetzt = prompt_tokens_schaetzen(system, user)
    fenster = kontextfenster()
    if fenster and geschaetzt > fenster:
        info["kontext"] = _kontext_ueberschritten(label, geschaetzt, geschaetzt=True)
    t0 = time.perf_counter()
    try:
        text, meta = fn(system, user, json_mode=json_mode)
    except Exception as e:
        record_timing(label, time.perf_counter() - t0,
                      {"fehler": f"{type(e).__name__}: {e}"[:200],
                       "prompt_tokens_geschaetzt": geschaetzt})
        raise LLMAufrufFehler(e, info) from e
    meta = dict(meta or {})
    meta["prompt_tokens_geschaetzt"] = geschaetzt
    gemessen = meta.get("prompt_tokens")
    if (fenster and "kontext" not in info and isinstance(gemessen, int)
            and gemessen >= fenster * 0.98):
        # Nachkontrolle: Liegt prompt_eval_count am Maximum, hat Ollama gekürzt.
        info["kontext"] = _kontext_ueberschritten(label, gemessen, geschaetzt=False)
    record_timing(label, time.perf_counter() - t0, meta)
    info["meta"] = meta
    log.debug("ANTWORT: %s", text)
    return schweizer_rechtschreibung(strip_reasoning(text)), info


def schweizer_rechtschreibung(text: str) -> str:
    """Ersetzt ß durch ss (T-03).

    Der Systemprompt verlangt Schweizer Rechtschreibung, Modelle halten sich
    aber nicht immer daran («beißt»). Weil jeder Text aus dem Sprachmodell
    hier vorbeikommt, bevor er geparst, gespeichert oder angezeigt wird,
    genügt diese eine Stelle.
    """
    return text.replace("ß", "ss").replace("ẞ", "SS")


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

KORREKTUR_HINWEIS = (
    "\n\nKORREKTUR: Dein letzter Vorschlag verletzte eine Regel: {verstoss} "
    "Erzeuge einen neuen Vorschlag, der diese Regel einhält."
)


def chat_json(system: str, user: str, fallback: dict, check=None,
              versuche: int = 2, temperature: float | None = None) -> dict:
    """Siehe _chat_json; `temperature` gilt nur für diesen Aufruf."""
    token = _temperatur.set(temperature)
    try:
        return _chat_json(system, user, fallback, check, versuche)
    finally:
        _temperatur.reset(token)


def _chat_json(system: str, user: str, fallback: dict, check=None,
               versuche: int = 2) -> dict:
    """Wie chat(), erwartet aber JSON.

    Ablauf (T-01): Scheitert ein Aufruf technisch oder ist die Antwort kein
    lesbares JSON, wird er einmal wiederholt. Erst wenn auch das scheitert,
    greift der Fallback. Das Ergebnis trägt dann `_fallback` und `_fehler`,
    damit der Aufrufer ein Event fallback_used protokollieren kann.

    T-09: Eine leere Antwort ist ein eigener Fehlerfall. Der nächste Versuch
    ist dann nicht identisch: Er verzichtet auf format=json (das JSON wird
    danach mit extract_json repariert) und bittet ausdrücklich um eine direkte
    Antwort ohne Vorüberlegungen. Die Metadaten der Antwort (done_reason,
    Tokenzahlen, Dauer) landen im Log und im Fallback.

    `check` ist eine optionale Prüffunktion (dict -> str | None). Meldet sie
    einen Regelverstoss, wird einmal mit einem Korrekturhinweis neu generiert.
    Verstösst auch der zweite Versuch, wird er trotzdem verwendet und der
    Verstoss in `_verstoesse` mitgegeben.
    """
    label = _label(user)
    fehler: list[str] = []
    verstoesse: list[str] = []
    beste: dict | None = None
    kontext: dict | None = None
    fehlerart: str | None = None
    antwort_meta: dict | None = None
    roh: dict | None = None
    prompt = user
    json_mode = True
    for versuch in range(1, versuche + 1):
        try:
            text, info = _chat_mit_info(system, prompt, json_mode=json_mode)
        except Exception as e:
            ursache = e.original if isinstance(e, LLMAufrufFehler) else e
            kontext = kontext or (e.info.get("kontext") if isinstance(e, LLMAufrufFehler) else None)
            grund = f"{type(ursache).__name__}: {ursache}"[:300]
            log.error("LLM-Fehler (%s, Versuch %d): %s", label, versuch, grund)
            fehler.append(grund)
            fehlerart = "technisch"
            continue
        kontext = kontext or info.get("kontext")
        meta = info.get("meta") or {}
        if not text.strip():
            antwort_meta = _meta_kurz(meta)
            grund = "leere Antwort" + (f" ({_meta_text(antwort_meta)})" if antwort_meta else "")
            log.warning("%s (%s, Versuch %d)", grund, label, versuch)
            _mark_last_error(label, "leere Antwort")
            fehler.append(grund)
            fehlerart = "leere_antwort"
            # Zweiter Versuch mit veränderter Anfrage statt identisch zu wiederholen
            json_mode = False
            prompt = user + LEER_HINWEIS
            continue
        parsed = extract_json(text)
        if not isinstance(parsed, dict):
            antwort_meta = _meta_kurz(meta)
            grund = f"Antwort war kein lesbares JSON: {text[:120]!r}"
            log.warning("%s (%s, Versuch %d%s)", grund, label, versuch,
                        f", {_meta_text(antwort_meta)}" if antwort_meta else "")
            _mark_last_error(label, "JSON nicht lesbar")
            fehler.append(grund)
            fehlerart = "json_unlesbar"
            continue
        # T-10: Zuerst Felder und Typen, dann die didaktischen Regeln
        verstoss = didaktik.struktur_pruefen(parsed, label) or (check(parsed) if check else None)
        if verstoss:
            verstoesse.append(verstoss)
            if didaktik.ist_strukturfehler(verstoss):
                # Eine falsche Struktur wird nie verwendet: lieber der Fallback
                log.warning("Strukturfehler (%s, Versuch %d): %s", label, versuch, verstoss)
                fehler.append(verstoss)
                fehlerart = "struktur"
                roh = parsed           # für Aufrufer, die Teile retten können (Einstufung)
            else:
                log.info("Regelverstoss (%s, Versuch %d): %s", label, versuch, verstoss)
                beste = parsed
            if versuch < versuche:
                prompt = user + KORREKTUR_HINWEIS.format(verstoss=verstoss)
                continue
            if beste is not parsed:
                break
            return _mit_meta(parsed, versuch, fehler, verstoesse, offen=True)
        return _mit_meta(parsed, versuch, fehler, verstoesse)
    if beste is not None:
        return _mit_meta(beste, versuche, fehler, verstoesse, offen=True)
    out = dict(fallback)
    out["_fallback"] = True
    out["_fehler"] = " | ".join(fehler) or "unbekannt"
    out["_fehlerart"] = fehlerart or "unbekannt"
    if roh is not None:
        out["_roh"] = roh
    if antwort_meta:
        out["_antwort_meta"] = antwort_meta
    if kontext:
        # T-08: Ursache sichtbar machen, statt nur «kein lesbares JSON» zu melden
        out["_kontext"] = kontext
        out["_fehler"] = ("Kontext zu gross (Prompt " + ("ca. " if kontext["geschaetzt"] else "")
                          + f"{kontext['prompt_tokens']} Tokens, Maximum {kontext['max_tokens']}). "
                          + out["_fehler"])
    record_fallback(label, out["_fehler"], kontext)
    return out


# T-09: zweiter Versuch nach einer leeren Antwort. «/no_think» ist der
# Schalter von Qwen3, um den Denkmodus im Prompt abzuschalten; andere Modelle
# lesen es als harmlosen Text.
LEER_HINWEIS = ("\n\nWICHTIG: Deine letzte Antwort war leer. Antworte jetzt direkt und ohne "
                "Vorüberlegungen mit genau einem JSON-Objekt im verlangten Format. /no_think")

_META_FELDER = ("done_reason", "prompt_tokens", "antwort_tokens", "gesamt_sekunden",
                "thinking_zeichen", "aus_thinking")


def _meta_kurz(meta: dict) -> dict:
    return {k: meta[k] for k in _META_FELDER if meta.get(k) is not None}


def _meta_text(m: dict) -> str:
    teile = []
    if m.get("done_reason"):
        teile.append(f"done_reason={m['done_reason']}")
    if m.get("prompt_tokens") is not None:
        teile.append(f"Prompt {m['prompt_tokens']} Tokens")
    if m.get("antwort_tokens") is not None:
        teile.append(f"Antwort {m['antwort_tokens']} Tokens")
    if m.get("gesamt_sekunden") is not None:
        teile.append(f"{m['gesamt_sekunden']} s")
    if m.get("thinking_zeichen"):
        teile.append(f"{m['thinking_zeichen']} Zeichen im Feld thinking")
    return ", ".join(teile)


def _mit_meta(data: dict, versuch: int, fehler: list, verstoesse: list,
              offen: bool = False) -> dict:
    data["_versuche"] = versuch
    if offen:
        data["_verstoss_offen"] = True      # das verwendete Ergebnis verletzt eine Regel
    if fehler:
        data["_fehler_vorher"] = fehler
    if verstoesse:
        data["_verstoesse"] = verstoesse
    return data


def public(data: dict) -> dict:
    """Entfernt interne Metadaten (Schlüssel mit _) vor der Auslieferung."""
    return {k: v for k, v in data.items() if not k.startswith("_")}


_JSON_ESCAPES = set('"\\/bfnrtu')


def repair_json_text(raw: str) -> str:
    r"""Repariert typische Fehler von Sprachmodellen in JSON-Zeichenketten.

    Das Hauptproblem sind LaTeX-Befehle: Ein Modell schreibt "$\Delta x$" mit
    einem einzelnen Backslash. Für JSON ist \D eine ungültige Escape-Sequenz,
    das Parsen scheitert und der Tutor fällt auf den Fallback zurück. Noch
    tückischer ist "$\frac{a}{b}$": \f ist ein gültiges Escape (Seitenvorschub),
    das Parsen gelingt, aber die Formel ist still zerstört.

    Deshalb: Innerhalb von Zeichenketten wird in Formelbereichen ($...$,
    $$...$$, \(...\), \[...\]) jeder einzelne Backslash verdoppelt, ausserhalb
    nur jene, die kein gültiges JSON-Escape einleiten.
    """
    out: list[str] = []
    in_str = False
    math = False
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if not in_str:
            if c == '"':
                in_str, math = True, False
            out.append(c)
            i += 1
            continue
        if c == "\\":
            nxt = raw[i + 1] if i + 1 < n else ""
            if nxt == "\\":                      # bereits korrekt escaped
                out.append("\\\\")
                i += 2
                continue
            if nxt and nxt in "([":                     # \( oder \[ öffnet Formel
                math = True
                out.append("\\\\" + nxt)
                i += 2
                continue
            if nxt and nxt in ")]":
                math = False
                out.append("\\\\" + nxt)
                i += 2
                continue
            if nxt == '"':                        # escaptes Anführungszeichen
                out.append('\\"')
                i += 2
                continue
            if math or nxt not in _JSON_ESCAPES:
                out.append("\\\\")
                i += 1
                continue
            if nxt == "u" and not re.match(r"[0-9a-fA-F]{4}", raw[i + 2:i + 6]):
                out.append("\\\\")                  # \underline statt \u00e4
                i += 1
                continue
            out.append(c + nxt)
            i += 2
            continue
        if c == "$":
            if raw.startswith("$$", i):
                math = not math
                out.append("$$")
                i += 2
                continue
            math = not math
        elif c == '"':
            in_str = False
        out.append(c)
        i += 1
    return "".join(out)


def _find_object(text: str) -> str | None:
    """Findet das erste vollständige JSON-Objekt; Klammern in Zeichenketten zählen nicht."""
    start = text.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract_json(text: str):
    """Extrahiert das erste JSON-Objekt aus einem Text (auch in ```-Blöcken).

    Robust gegenüber LaTeX-Backslashes, rohen Zeilenumbrüchen in Zeichenketten
    und einem abschliessenden Komma vor } oder ].
    """
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    candidate = _find_object(text)
    if candidate is None:
        return None
    repaired = repair_json_text(candidate)
    for attempt in (repaired, re.sub(r",\s*([}\]])", r"\1", repaired)):
        try:
            return json.loads(attempt, strict=False)
        except json.JSONDecodeError:
            continue
    return None
