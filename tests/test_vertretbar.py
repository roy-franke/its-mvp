"""D-15: Vertretbare Alternativen, Umgang mit Nichtwissen, Widerspruch (Auftrag 3).

Fall 1 aus Anhang B: Schaukel bricht auf einem Spielplatz der Stadt ab,
Antwort «Hersteller der Schaukel Produktehaftpflicht».
"""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
NUR_MATERIAL = dict(LESSON, einstellungen={"wissensstufen": ["material"]})
MIT_WISSEN = dict(LESSON, einstellungen={"wissensstufen": ["material", "allgemeinwissen"]})

FALL1 = {
    "typ": "aufgabe", "titel": "Unfall auf dem Spielplatz",
    "inhalt": "Ein Kind spielt auf einem Spielplatz. Während des Spiels bricht eine Schaukel ab und das Kind "
              "verletzt sich. Der Spielplatz wird von einer Stadtverwaltung betrieben.",
    "frage": "Wer ist für den Schaden verantwortlich und welche Art der Haftung greift hier?",
    "erwartete_antwort": "Die Stadt als Werkeigentümerin haftet nach Art. 58 OR, eine Kausalhaftung.",
    "erwartete_elemente": [{"dimension": "verantwortliche Person", "erwartet": "die Stadt als Werkeigentümerin"},
                           {"dimension": "Art der Haftung", "erwartet": "Werkeigentümerhaftung, eine Kausalhaftung"}],
    "konzept": "Werkeigentümerhaftung",
}
ANTWORT1 = "Hersteller der Schaukel Produktehaftpflicht"


def _modell(antwort: dict, prompts: list):
    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(antwort), {}
    return p


VERTRETBAR = {
    "elemente": [
        {"element": "verantwortliche Person", "status": "vertretbar", "antwort": "Hersteller der Schaukel",
         "annahme": "die Schaukel war fehlerhaft hergestellt", "begruendung": "Der Fall sagt nicht, warum sie brach."},
        {"element": "Art der Haftung", "status": "vertretbar", "antwort": "Produktehaftpflicht",
         "annahme": "Herstellungsfehler", "ausserhalb_material": True,
         "begruendung": "Die Produktehaftpflicht ist verschuldensunabhängig."}],
    "sachlicher_widerspruch": False, "bewertung": "korrekt",
    "feedback": "Das ist vertretbar, wenn die Schaukel fehlerhaft hergestellt wurde. Der Fall sagt dazu nichts. "
                "Naheliegender ist hier die Haftung der Stadt als Werkeigentümerin.", "hinweis": ""}


def test_status_vertretbar_zaehlt_wie_korrekt_nicht_beurteilbar_wie_ungenau():
    assert didaktik.urteil_aus_elementen([{"status": "vertretbar"}, {"status": "korrekt"}]) == "korrekt"
    assert didaktik.urteil_aus_elementen([{"status": "nicht_beurteilbar"}, {"status": "korrekt"}]) == "teilweise"
    assert didaktik.urteil_aus_elementen([{"status": "nicht_beurteilbar"}]) == "teilweise"
    assert didaktik.urteil_aus_elementen([{"status": "vertretbar"}, {"status": "falsch"}]) == "falsch"


def test_ak1_vertretbare_antwort_wird_nicht_als_falsch_bewertet(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(VERTRETBAR, prompts))
    r = tutor.evaluate_answer(MIT_WISSEN, tutor.new_profile(), FALL1, ANTWORT1)
    assert r["bewertung"] == "korrekt"
    assert r["elemente"][0]["annahme"] == "die Schaukel war fehlerhaft hergestellt"
    assert r["elemente"][1]["ausserhalb_material"] is True
    user = prompts[0]
    assert "vertretbar = weicht von der erwarteten Lösung ab" in user
    assert "Eine Abweichung von der erwarteten Lösung allein ist NICHT falsch" in user
    assert "prüfe es mit gesichertem Allgemeinwissen" in user


def test_ak3_nur_material_kennt_nicht_beurteilbar(monkeypatch):
    prompts = []
    antwort = dict(VERTRETBAR, bewertung="teilweise", feedback="Die Produktehaftpflicht kommt im Material nicht "
                   "vor; das kann ich nicht abschliessend beurteilen.", hinweis="Was sagt das Material zur Stadt?")
    antwort["elemente"] = [dict(e, status="nicht_beurteilbar") for e in VERTRETBAR["elemente"]]
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(antwort, prompts))
    r = tutor.evaluate_answer(NUR_MATERIAL, tutor.new_profile(), FALL1, ANTWORT1)
    assert r["bewertung"] == "teilweise"           # nie «falsch»
    assert "nicht_beurteilbar = geht über das Lektionsmaterial hinaus" in prompts[0]
    assert "Allgemeinwissen" not in prompts[0].split("2. Prüfe")[1].split("fehlt =")[0]


def test_alternative_loesungen_gehen_an_die_bewertung(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell(VERTRETBAR, prompts))
    tutor.evaluate_answer(LESSON, tutor.new_profile(),
                          dict(FALL1, alternative_loesungen=["Der Hersteller nach Produktehaftpflichtgesetz"]),
                          ANTWORT1)
    assert "Weitere vertretbare Lösungen" in prompts[0] and "Produktehaftpflichtgesetz" in prompts[0]


def test_systemprompt_benennt_nichtwissen_fuer_alle_schritte():
    sp = tutor._system_prompt(LESSON)
    assert "Erfinde keine Angaben zum Sachverhalt" in sp and "nie falsch, nur weil sie" in sp


def test_ak6_chat_prueft_alternative_ernsthaft(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", _modell({"antwort": "Das wäre möglich, wenn …"}, prompts))
    tutor.answer_question(LESSON, tutor.new_profile(), FALL1,
                          "Wieso könnte dies nicht auch ein Fall von Produktehaftpflicht sein?", [])
    assert "prüfe sie ernsthaft am Sachverhalt" in prompts[0] and "Erfinde keine Angaben" in prompts[0]


def _sequenz_bis_aufgabe(c, name):
    c.post("/api/learner/login", json={"name": name})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    return sid


def test_ak4_ak5_widerspruch_einmal_ohne_versuch_mit_protokoll():
    c = TestClient(app)
    sid = _sequenz_bis_aufgabe(c, "Einwand")
    a = c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist.", "confidence": 4}).json()
    assert a["bewertung"] == "teilweise" and [z["id"] for z in a["zusatz"]] == ["widerspruch"]
    assert c.post(f"/api/session/{sid}/wahl", json={"wahl": "widerspruch", "text": " "}).status_code == 400
    r = c.post(f"/api/session/{sid}/wahl", json={"wahl": "widerspruch",
                                                 "text": "Das stimmt doch, der Fall lässt das offen."}).json()
    assert r["bewertung"] == "korrekt" and r["neubewertung"] == {"art": "widerspruch", "geaendert": True}
    p = c.get(f"/api/session/{sid}/state").json()["progress"]
    assert p["correct"] == 1 and p["partial"] == 0              # ersetzt, kein zusätzlicher Versuch
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    w = [e["payload"] for e in events if e["type"] == "widerspruch_lernende"]
    assert w and w[0]["urteil_vorher"] == "teilweise" and w[0]["urteil_nachher"] == "korrekt" and w[0]["geaendert"]
    alt = [e["payload"] for e in events if e["type"] == "alternative_anerkannt"]
    assert alt and alt[0]["status"] == "vertretbar" and alt[0]["annahme"]
    bew = [e["payload"] for e in events if e["type"] == "answer_evaluated"]
    assert bew[-1]["neubewertung"] == "widerspruch" and bew[-1]["versuch"] == 1


def test_ak5_widerspruch_ohne_aenderung_und_nur_einmal():
    c = TestClient(app)
    sid = _sequenz_bis_aufgabe(c, "Einwand2")
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist.", "confidence": 4})
    r = c.post(f"/api/session/{sid}/wahl", json={"wahl": "widerspruch", "text": "Ich finde, das reicht."}).json()
    assert r["bewertung"] == "teilweise" and r["neubewertung"]["geaendert"] is False
    assert "Ich bleibe bei meiner Bewertung" in r["feedback"]
    assert [w["id"] for w in r["wahl"]] == ["ergaenzen", "loesung", "weiter"] and r["zusatz"] == []
    assert c.post(f"/api/session/{sid}/wahl", json={"wahl": "widerspruch", "text": "Nochmals."}).status_code == 409
    p = c.get(f"/api/session/{sid}/state").json()["progress"]
    assert p["partial"] == 1 and p["correct"] == 0


def test_widerspruch_nach_falsch_bleibt_beim_zweiten_versuch():
    c = TestClient(app)
    sid = _sequenz_bis_aufgabe(c, "Einwand3")
    a = c.post(f"/api/session/{sid}/answer", json={"answer": "weiss nicht", "confidence": 2}).json()
    assert a["bewertung"] == "falsch" and a["adaption"] == "retry" and a["zusatz"][0]["id"] == "widerspruch"
    r = c.post(f"/api/session/{sid}/wahl", json={"wahl": "widerspruch", "text": "Das ist vertretbar."}).json()
    assert r["bewertung"] == "korrekt"
    st = c.get(f"/api/session/{sid}/state").json()
    assert st["progress"]["wrong"] == 0 and st["progress"]["correct"] == 1 and st["wartet_auf"] == "weiter"
