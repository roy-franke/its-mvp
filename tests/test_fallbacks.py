"""T-01: Wiederholung, brauchbare Fallbacks, Protokollierung und Vorabruf."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

client = TestClient(app)

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())


class FlakyProvider:
    """Mock-Provider, der die ersten `fail` Aufrufe scheitern lässt."""

    def __init__(self, fail: int = 1, labels: set | None = None):
        self.fail = fail
        self.labels = labels
        self.calls = 0

    def __call__(self, system, user, json_mode=False):
        label = llm._label(user)
        if self.labels is None or label in self.labels:
            self.calls += 1
            if self.calls <= self.fail:
                raise llm.LLMError("simulierter Ausfall")
        return llm._mock_text(system, user), {}


@pytest.fixture
def provider(monkeypatch):
    def _set(p):
        monkeypatch.setitem(llm._PROVIDERS, "mock", p)
        return p
    return _set


def _profile(level="basic"):
    p = tutor.new_profile()
    p["level"] = level
    return p


# ---------------------------------------------------------------- AK 1

def test_erster_aufruf_scheitert_zweiter_wird_verwendet(provider):
    p = provider(FlakyProvider(fail=1))
    data = tutor.generate_theory(LESSON, _profile(), [])
    assert p.calls == 2
    assert not data.get("_fallback")
    assert data["titel"] == "Grundprinzip der Verschuldenshaftung"
    assert data["_versuche"] == 2
    assert "simulierter Ausfall" in data["_fehler_vorher"][0]


def test_unlesbares_json_wird_wiederholt(provider):
    antworten = iter(["Das ist kein JSON", json.dumps({"antwort": "Jetzt klappt es."})])
    provider(lambda s, u, json_mode=False: (next(antworten), {}))
    data = llm.chat_json("sys", "AUFGABE: FRAGE_BEANTWORTEN\nx", fallback={"antwort": "fb"})
    assert data["antwort"] == "Jetzt klappt es."


# ---------------------------------------------------------------- AK 2

def test_theorie_fallback_zeigt_echten_materialtext(provider):
    provider(FlakyProvider(fail=99))
    data = tutor.generate_theory(LESSON, _profile(), [])
    assert data["_fallback"] and data["typ"] == "theorie"
    abschnitt = data["inhalt"].split("\n\n", 1)[1]
    # Der angezeigte Abschnitt stammt wörtlich aus dem Material
    assert abschnitt[:80] in " ".join(LESSON["material"].split())
    assert len(abschnitt) > 100


def test_ohne_material_ehrliche_fehlermeldung(provider):
    provider(FlakyProvider(fail=99))
    leer = dict(LESSON, material="")
    data = tutor.generate_theory(leer, _profile(), [])
    assert data["typ"] == "fehler" and data["wiederholbar"] is True
    assert "technischen Problems" in data["inhalt"]


def test_aufgaben_fallback_ist_brauchbar(provider):
    provider(FlakyProvider(fail=99))
    p = _profile("intermediate")
    data = tutor.generate_task(LESSON, p, [])
    assert data["typ"] == "aufgabe" and data["frage"]
    assert data["inhalt"].split("\n\n", 1)[1][:60] in " ".join(LESSON["material"].split())


def test_fallback_zeigt_nacheinander_verschiedene_abschnitte(provider):
    provider(FlakyProvider(fail=99))
    p = _profile()
    a = tutor.generate_theory(LESSON, p, [])
    p["fallback_abschnitte"] = [a["material_abschnitt"]]
    b = tutor.generate_theory(LESSON, p, [])
    assert a["material_abschnitt"] != b["material_abschnitt"]


def test_nochmals_versuchen_ueber_die_api(provider, monkeypatch):
    flaky = provider(FlakyProvider(fail=99, labels={"THEORIE_SCHRITT"}))
    r = client.post("/api/session/start", json={"name": "Fallback-Test"}).json()
    sid = r["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    # Material der Lektion leeren, damit kein Abschnitt bestimmbar ist
    from app import main
    original = main.load_lesson
    monkeypatch.setattr(main, "load_lesson", lambda lid: dict(original(lid), material=""))
    t = client.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] == "fehler"
    assert t["progress"]["theory_steps"] == 0
    # «Nochmals versuchen»: Provider funktioniert wieder
    flaky.fail = 0
    t2 = client.post(f"/api/session/{sid}/next").json()
    assert t2["task"]["typ"] == "theorie"
    assert not t2["task"].get("fallback")


def test_bewertungsfehler_zaehlt_nicht_als_falsch(provider):
    r = client.post("/api/session/start", json={"name": "Bewertungsausfall"}).json()
    sid = r["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        t = client.post(f"/api/session/{sid}/next").json()
        if t["task"]["typ"] == "aufgabe":
            break
    provider(FlakyProvider(fail=99, labels={"ANTWORT_BEWERTEN"}))
    a = client.post(f"/api/session/{sid}/answer", json={"answer": "x" * 50}).json()
    assert a["bewertung"] == "unbewertet"
    assert a["adaption"] == "retry"
    assert a["progress"]["wrong"] == 0 and a["progress"]["step"] == 0


# ---------------------------------------------------------------- AK 3

ALTE_TEXTE = [
    "Lies den folgenden Abschnitt aus dem Material noch einmal aufmerksam.",
    "Hier ist die Erklärung:",
    "Die wichtigsten Punkte findest du weiter unten.",
]


@pytest.mark.parametrize("text", ALTE_TEXTE)
def test_pruefung_erkennt_leere_ankuendigungen(text):
    assert didaktik.leere_ankuendigung(text)


@pytest.mark.parametrize("text", [
    "Beachte folgende Punkte: Schaden und Verschulden. Beide müssen vorliegen.",
    "Der Ball fällt von oben nach unten.",
    "Daraus folgt, dass Anna haftet.",
    "",
])
def test_pruefung_laesst_korrekte_texte_durch(text):
    assert didaktik.leere_ankuendigung(text) is None


def _alle_fallback_texte():
    for key, felder in tutor.FALLBACK_TEXTE.items():
        for feld, wert in felder.items():
            if isinstance(wert, str):
                yield f"{key}.{feld}", wert


@pytest.mark.parametrize("name,text", list(_alle_fallback_texte()))
def test_kein_fallback_text_kuendigt_leer_an(name, text):
    assert didaktik.leere_ankuendigung(text) is None, name


def test_zusammengesetzte_fallbacks_ohne_leere_ankuendigung(provider):
    provider(FlakyProvider(fail=99))
    for data in (tutor.generate_theory(LESSON, _profile(), []),
                 tutor.generate_task(LESSON, _profile("advanced"), []),
                 tutor.generate_theory(dict(LESSON, material=""), _profile(), [])):
        assert didaktik.pruefe_felder(data, ("inhalt", "frage")) is None


def test_leere_ankuendigung_fuehrt_zu_neugenerierung(provider):
    antworten = iter([
        json.dumps({"titel": "T", "inhalt": "Lies den folgenden Abschnitt genau.", "konzept": "K"}),
        json.dumps({"titel": "T", "inhalt": "Ein Schaden ist eine Vermögensminderung.", "konzept": "K"}),
    ])
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return next(antworten), {}
    provider(p)
    data = tutor.generate_theory(LESSON, _profile(), [])
    assert data["inhalt"] == "Ein Schaden ist eine Vermögensminderung."
    assert "KORREKTUR" in prompts[1]
    assert data["_verstoesse"]


# ---------------------------------------------------------------- AK 4

def test_fallback_event_und_messuebersicht(provider):
    llm.reset_timings()
    r = client.post("/api/session/start", json={"name": "Fallback-Event"}).json()
    sid = r["session_id"]
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    provider(FlakyProvider(fail=99, labels={"THEORIE_SCHRITT"}))
    t = client.post(f"/api/session/{sid}/next").json()
    assert t["task"]["fallback"] is True
    events = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    fb = [e for e in events if e["type"] == "fallback_used"]
    assert fb and fb[0]["payload"]["schrittart"] == "THEORIE_SCHRITT"
    assert "simulierter Ausfall" in fb[0]["payload"]["grund"]
    z = {r["schritt"]: r for r in client.get("/api/teacher/timings").json()["zusammenfassung"]}
    assert z["THEORIE_SCHRITT"]["fallbacks"] == 1
    assert z["THEORIE_SCHRITT"]["fehler"] == 2   # beide Versuche gescheitert


# ---------------------------------------------------------------- AK 5

def _bis_theorie(sid):
    client.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t = client.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] == "theorie"


def test_vorabruf_wird_ohne_zwischenfrage_uebernommen(provider):
    r = client.post("/api/session/start", json={"name": "Vorabruf-1"}).json()
    sid = r["session_id"]
    _bis_theorie(sid)
    zaehler = provider(FlakyProvider(fail=0, labels={"NAECHSTE_AUFGABE"}))
    pre = client.post(f"/api/session/{sid}/next?prefetch=true").json()
    assert pre["vorabruf"] is True
    # Vorabruf verändert den Lernverlauf nicht
    ev = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert sum(1 for e in ev if e["type"] == "task") == 1
    t = client.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] == "aufgabe"
    assert zaehler.calls == 1          # kein zweites Erzeugen


def test_vorabruf_nach_verstaendnisfrage_wird_neu_erzeugt(provider):
    r = client.post("/api/session/start", json={"name": "Vorabruf-2"}).json()
    sid = r["session_id"]
    _bis_theorie(sid)
    zaehler = provider(FlakyProvider(fail=0, labels={"NAECHSTE_AUFGABE"}))
    client.post(f"/api/session/{sid}/next?prefetch=true")
    client.post(f"/api/session/{sid}/chat", json={"message": "Was heisst adäquat?"})
    t = client.post(f"/api/session/{sid}/next").json()
    assert t["task"]["typ"] == "aufgabe"
    assert zaehler.calls == 2          # veralteter Vorabruf verworfen, neu erzeugt
    ev = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    verworfen = [e for e in ev if e["type"] == "vorabruf_verworfen"]
    assert verworfen and "Gesprächsstand" in verworfen[0]["payload"]["grund"]
    # Die neu erzeugte Aufgabe kennt die Verständnisfrage
    typen = [e["type"] for e in ev]
    assert typen.index("chat_question") < max(i for i, t in enumerate(typen) if t == "task")


def test_vorabruf_mit_anderer_adaption_wird_verworfen(provider):
    r = client.post("/api/session/start", json={"name": "Vorabruf-3"}).json()
    sid = r["session_id"]
    _bis_theorie(sid)
    client.post(f"/api/session/{sid}/next?prefetch=true")
    client.post(f"/api/session/{sid}/next?adaptation=advance")
    ev = client.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert any(e["type"] == "vorabruf_verworfen" for e in ev)


# ---------------------------------------------------------------- JSON-Reparatur

@pytest.mark.parametrize("raw,feld,erwartet", [
    ('{"inhalt": "Es gilt $\\Delta x \\cdot \\Delta p \\geq \\frac{h}{4\\pi}$."}',
     "inhalt", "Es gilt $\\Delta x \\cdot \\Delta p \\geq \\frac{h}{4\\pi}$."),
    ('{"inhalt": "Zeile 1\nZeile 2"}', "inhalt", "Zeile 1\nZeile 2"),
    ('{"inhalt": "Bruch $\\\\frac{a}{b}$ korrekt escaped"}', "inhalt",
     "Bruch $\\frac{a}{b}$ korrekt escaped"),
    ('{"inhalt": "Menge \\{1, 2\\} mit Klammer"}', "inhalt", "Menge \\{1, 2\\} mit Klammer"),
    ('{"inhalt": "Umlaut \\u00e4 und Zitat \\"x\\""}', "inhalt", 'Umlaut ä und Zitat "x"'),
    ('{"liste": [1, 2,],}', "liste", [1, 2]),
])
def test_json_reparatur(raw, feld, erwartet):
    assert llm.extract_json(raw)[feld] == erwartet


def test_ollama_erzwingt_json_nur_wo_json_erwartet(monkeypatch):
    monkeypatch.delenv("OLLAMA_FORMAT_JSON", raising=False)
    assert llm.ollama_payload("s", "u", json_mode=True)["format"] == "json"
    assert "format" not in llm.ollama_payload("s", "u")
    monkeypatch.setenv("OLLAMA_FORMAT_JSON", "false")
    assert "format" not in llm.ollama_payload("s", "u", json_mode=True)
