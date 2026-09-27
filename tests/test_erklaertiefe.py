"""D-03: Erklärtiefe, Eskalation bei Nachfragen, Ton und Allgemeinwissen."""

import json

import pytest
from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import LESSONS_DIR, app

lp = TestClient(app)


def _bis_theorie(c, name, lesson_id="haftungsrecht"):
    sid = c.post("/api/session/start", json={"name": name, "lesson_id": lesson_id}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    t = c.post(f"/api/session/{sid}/next").json()["task"]
    assert t["typ"] == "theorie"
    return sid


class Spy:
    def __init__(self, antworten=None):
        self.prompts = []
        self.antworten = list(antworten or [])

    def __call__(self, system, user, json_mode=False):
        self.prompts.append(user)
        if "FRAGE_BEANTWORTEN" in user and self.antworten:
            return self.antworten.pop(0), {}
        return llm._mock_text(system, user), {}

    def chat_prompts(self):
        return [p for p in self.prompts if "FRAGE_BEANTWORTEN" in p]


# ---------------------------------------------------------------- AK 2 Eskalation

def test_drei_nachfragen_durchlaufen_die_stufen(monkeypatch):
    spy = Spy()
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = _bis_theorie(c, "Eskalation")
    r1 = c.post(f"/api/session/{sid}/chat", json={"message": "genauer", "art": "genauer"}).json()
    r2 = c.post(f"/api/session/{sid}/chat", json={"message": "genauer", "art": "genauer"}).json()
    r3 = c.post(f"/api/session/{sid}/chat", json={"message": "genauer", "art": "genauer"}).json()
    assert [r1["stufe"], r2["stufe"], r3["stufe"]] == [1, 2, 3]
    prompts = spy.chat_prompts()
    assert len(prompts) == 2                       # Stufe 3 braucht kein Sprachmodell
    assert "ESKALATIONSSTUFE: 1" in prompts[0] and "Mechanismus" in prompts[0]
    assert "ESKALATIONSSTUFE: 2" in prompts[1] and "Analogie" in prompts[1]
    assert "alles gezeigt" in r3["antwort"] and r3["angebot"] == "allgemeinwissen"
    # Bereits Gezeigtes geht mit, damit es nicht wiederholt wird
    assert "Bereits gezeigt" in prompts[0] and "vier Voraussetzungen" in prompts[0]
    assert r1["antwort"][:40] in prompts[1]
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    stufen = [e["payload"]["stufe"] for e in events if e["type"] == "chat_reply"]
    assert stufen == [1, 2, 3]


def test_zaehlung_pro_konzept():
    p = tutor.new_profile()
    assert [tutor.eskalationsstufe(p, "A") for _ in range(4)] == [1, 2, 3, 3]
    assert tutor.eskalationsstufe(p, "B") == 1


def test_theorie_dazu_stufe1_verlangt_neuen_zugang(monkeypatch):
    spy = Spy()
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = _bis_theorie(c, "Neuer Zugang")
    c.post(f"/api/session/{sid}/chat", json={"message": "Theorie", "art": "theorie"})
    assert "NEUEN Zugang" in spy.chat_prompts()[0]


# ---------------------------------------------------------------- Ähnlichkeit und Ton

def test_wiederholung_der_theorie_wird_neu_generiert(monkeypatch):
    theorie = json.loads(llm._mock_text("", "AUFGABE: THEORIE_SCHRITT"))
    kopie = json.dumps({"antwort": theorie["inhalt"], "konzept": "", "ausserhalb_material": False})
    spy = Spy([kopie])
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = _bis_theorie(c, "Wiederholung")
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Theorie", "art": "theorie"}).json()
    assert r["antwort"] != theorie["inhalt"]
    assert "KORREKTUR" in spy.chat_prompts()[1] and "wiederholt" in spy.chat_prompts()[1]


def test_defensiver_einstieg_wird_neu_generiert(monkeypatch):
    defensiv = json.dumps({"antwort": "Im Material wird nicht erwähnt, dass man zwischen Wellen und "
                                      "Teilchen umschalten kann.", "konzept": ""})
    spy = Spy([defensiv])
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = _bis_theorie(c, "Defensiv")
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Kann man umschalten?"}).json()
    assert not r["antwort"].startswith("Im Material")
    assert "defensiv" in spy.chat_prompts()[1]


@pytest.mark.parametrize("text", [
    "Im Material wird nicht erwähnt, dass man umschalten kann.",
    "Das Material enthält keine weiteren Beispiele.",
    "Laut Material ist das nicht vorgesehen.",
    "Das Lektionsmaterial nennt keine Bauweise.",
])
def test_defensive_formulierungen_erkannt(text):
    assert didaktik.defensiver_einstieg(text)


@pytest.mark.parametrize("text", [
    "Nein, umschalten kann man nicht. Licht zeigt je nach Versuch beide Eigenschaften.",
    "Dazu sagt das Lektionsmaterial nichts. Ich kann dir aber erklären, wie ein Sensor misst.",
])
def test_klare_formulierungen_erlaubt(text):
    assert didaktik.defensiver_einstieg(text) is None


def test_aehnlichkeit():
    a = "Ein Teilchen kann sich in mehreren Zuständen gleichzeitig befinden, bis gemessen wird."
    assert didaktik.aehnlichkeit(a, [a]) == 1.0
    assert didaktik.zu_aehnlich(a + " Das nennt man Überlagerung der Zustände.", [a])
    assert didaktik.zu_aehnlich("Stell dir eine Münze vor, die sich dreht: Solange sie wirbelt, "
                                "ist sie weder Kopf noch Zahl, erst beim Auffangen entscheidet es sich.",
                                [a]) is None


# ---------------------------------------------------------------- Allgemeinwissen (E4)

@pytest.fixture
def nur_material():
    r = lp.post("/api/teacher/lessons", json={
        "titel": "Nur Material", "lernziele": ["Haftung erklären"],
        "material": "Die Verschuldenshaftung nach Art. 41 OR verlangt Schaden, Widerrechtlichkeit, "
                    "Kausalzusammenhang und Verschulden. " * 2,
        "einstellungen": {"wissensstufen": ["material"]}})
    lid = r.json()["id"]
    yield lid
    (LESSONS_DIR / f"{lid}.json").unlink(missing_ok=True)


def test_allgemeinwissen_angebot_und_kennzeichnung():
    c = TestClient(app)
    sid = _bis_theorie(c, "Allgemeinwissen")
    for _ in range(3):
        r = c.post(f"/api/session/{sid}/chat", json={"message": "mehr", "art": "theorie"}).json()
    assert r["angebot"] == "allgemeinwissen" and not r["ausserhalb_material"]
    r = c.post(f"/api/session/{sid}/chat", json={"message": "Ja", "art": "allgemeinwissen"}).json()
    assert r["ausserhalb_material"] is True
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert [e for e in events if e["type"] == "chat_reply"][-1]["payload"]["ausserhalb_material"]


def test_ohne_allgemeinwissen_hinweis_auf_lehrperson(nur_material, monkeypatch):
    spy = Spy()
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    c = TestClient(app)
    sid = _bis_theorie(c, "Nur Material", nur_material)
    for _ in range(3):
        r = c.post(f"/api/session/{sid}/chat", json={"message": "mehr", "art": "genauer"}).json()
    assert r["angebot"] == "lehrperson" and "Lehrperson" in r["antwort"]
    r = c.post(f"/api/session/{sid}/chat", json={"message": "trotzdem", "art": "allgemeinwissen"}).json()
    assert "ALLGEMEINWISSEN:" not in spy.chat_prompts()[-1]      # wird als normale Frage behandelt
    system = [p for p in spy.prompts]
    lesson = json.loads((LESSONS_DIR / f"{nur_material}.json").read_text(encoding="utf-8"))
    assert "Erkläre nur mit dem Lektionsmaterial" in tutor._system_prompt(lesson)
