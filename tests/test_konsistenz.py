"""D-18: Keine widersprüchlichen Aussagen des Tutors (Auftrag 3, Fall 2 aus Anhang B)."""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
BEWERTUNG = "Es geht hier nicht um Verschuldenshaftung, sondern um Kausalhaftung."
CHAT = "In diesem Fall handelt es sich nicht um Kausalhaftung, sondern um Verschuldenshaftung."
BALL = {"typ": "aufgabe", "titel": "Glasbruch im Park", "konzept": "Verschuldenshaftung",
        "inhalt": "Ein Junge spielt mit einem Ball im Park. Der Ball zerbricht eine Fensterscheibe.",
        "frage": "Wer ist verantwortlich für den Schaden und welche Art der Haftung greift hier?",
        "erwartete_antwort": "Der Junge haftet aus Verschuldenshaftung nach Art. 41 OR."}
HISTORY = [{"type": "task", "payload": BALL},
           {"type": "answer_evaluated", "payload": {"bewertung": "falsch", "feedback": BEWERTUNG, "hinweis": "",
                                                    "elemente": [{"element": "Art der Haftung", "status": "falsch",
                                                                  "begruendung": "Kausalhaftung erwartet."}]}}]


def test_ak3_gegensatz_nach_dem_muster_nicht_x_sondern_y():
    assert didaktik.gegensatz_zur_bewertung(BEWERTUNG, CHAT)
    assert didaktik.gegensatz_zur_bewertung(BEWERTUNG, "Es ist keine Kausalhaftung. Hier greift Verschuldenshaftung.") is None
    assert didaktik.gegensatz_zur_bewertung(BEWERTUNG, BEWERTUNG) is None
    v = didaktik.widerspruch_ungekennzeichnet(BEWERTUNG, {"antwort": CHAT, "widerspricht_bewertung": False})
    assert v and "geirrt" in v
    assert didaktik.widerspruch_ungekennzeichnet(
        BEWERTUNG, {"antwort": "Da habe ich mich vorhin geirrt: " + CHAT, "widerspricht_bewertung": True}) is None
    assert "ausdrücklich" in didaktik.widerspruch_ungekennzeichnet(
        BEWERTUNG, {"antwort": CHAT, "widerspricht_bewertung": True})


def test_chat_kennt_die_bewertung_und_verraet_die_loesung_nicht(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        prompts.append(u) or (json.dumps({"antwort": "Schau, wer den Ball geworfen hat.", "konzept": ""}), {})))
    profile = dict(tutor.new_profile(), wartet_auf="antwort")
    r = tutor.answer_question(LESSON, profile, BALL, "Wieso handelt es sich hier um Kausalhaftung?", HISTORY)
    user = prompts[0]
    assert "DEINE LETZTE BEWERTUNG DIESER AUFGABE" in user and "Urteil: falsch" in user and BEWERTUNG in user
    assert "die Aufgabe ist noch offen: nie verraten" in user               # AK 4
    assert "Da habe ich mich vorhin geirrt" in user and "widerspricht_bewertung" in user
    assert r["widerspricht_bewertung"] is False


def test_ak1_stiller_widerspruch_wird_neu_erzeugt_und_sonst_offen_gemacht(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (
        prompts.append(u) or (json.dumps({"antwort": CHAT, "konzept": "", "widerspricht_bewertung": False}), {})))
    r = tutor.answer_question(LESSON, dict(tutor.new_profile(), wartet_auf="antwort"), BALL,
                              "Wieso handelt es sich hier um Kausalhaftung?", HISTORY)
    assert "KORREKTUR" in prompts[1] and "Gegenteil deiner Bewertung" in prompts[1]
    assert r["widerspricht_bewertung"] is True and tutor.WIDERSPRUCH_OFFEN in r["antwort"]
    assert r["urteil_vorher"] == "falsch"


def test_kurzfassung_enthaelt_urteil_und_feedback():
    assert "Bewertung falsch: Es geht hier nicht um Verschuldenshaftung" in tutor._recent_history(HISTORY)


def test_ak2_neu_bewerten_zaehlt_nicht_als_versuch_und_ist_protokolliert():
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Selbstkorrektur"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil Schaden da ist.", "confidence": 5})
    d = c.post(f"/api/session/{sid}/chat", json={"message": "Ist das wirklich nur teilweise richtig?"}).json()
    assert d["widerspricht_bewertung"] and d["antwort"].startswith("Da habe ich mich vorhin geirrt")
    assert [z["id"] for z in d["zusatz"]] == ["neu_bewerten", "widerspruch"]
    assert [w["id"] for w in d["wahl"]] == ["ergaenzen", "loesung", "weiter"]
    r = c.post(f"/api/session/{sid}/wahl", json={"wahl": "neu_bewerten"}).json()
    assert r["bewertung"] == "korrekt" and r["neubewertung"] == {"art": "tutor_korrektur", "geaendert": True}
    p = c.get(f"/api/session/{sid}/state").json()["progress"]
    assert p["correct"] == 1 and p["partial"] == 0
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    typen = [e["type"] for e in events]
    assert "tutor_korrektur" in typen and "tutor_neubewertung" in typen
    k = [e["payload"] for e in events if e["type"] == "tutor_korrektur"][0]
    assert k["urteil_vorher"] == "teilweise" and k["neubewertung_angeboten"]
    neu = [e["payload"] for e in events if e["type"] == "answer_evaluated"][-1]
    assert neu["neubewertung"] == "tutor_korrektur" and neu["versuch"] == 1
    # Die Neubewertung erhält die Chat-Antwort als zusätzliche Sicht (Mock: «SELBSTKORREKTUR»)
    assert c.post(f"/api/session/{sid}/wahl", json={"wahl": "neu_bewerten"}).status_code == 409
