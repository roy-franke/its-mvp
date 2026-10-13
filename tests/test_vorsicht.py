"""D-16: Vorsichtige Formulierungen bei offenem Sachverhalt (Auftrag 3, Fall 3 aus Anhang B)."""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())

FALL3 = {
    "typ": "aufgabe", "titel": "Schaukel im Vereinsspielplatz",
    "inhalt": "Ein Kind spielt auf einem Spielplatz. Während des Spiels bricht ein Teil der Schaukel aus. Das Kind "
              "verletzt sich leicht. Der Spielplatz gehört einem Verein, der für die Wartung und Sicherheit "
              "verantwortlich ist.",
    "frage": "Welche Voraussetzung ist hier am stärksten erkennbar und warum?",
    "erwartete_antwort": "Die Verantwortung des Vereins als Werkeigentümer, weil er für Wartung und Sicherheit "
                         "zuständig ist; ein mangelhafter Unterhalt ist naheliegend.",
    "erwartete_elemente": [{"dimension": "Voraussetzung", "erwartet": "Verantwortung des Spielplatzbetreibers"},
                           {"dimension": "Begründung", "erwartet": "zuständig für Wartung und Sicherheit"}],
    "musterloesung_pruefung": {"ergebnis": "uebereinstimmend",
                               "offene_punkte": ["ob die Wartung der Schaukel vernachlässigt wurde"]},
}
A = ("Verantwortung des Spielplatzbetreibers / weil dieser für Sicherheit und Wartung zuständig ist / "
     "Vermutlich führte mangelnde Wartung der Schaukel zum Schaden.")
B = ("Verantwortung des Spielplatzbetreibers / weil dieser für Sicherheit und Wartung zuständig ist / "
     "Mangelnde Wartung der Schaukel verursachte den Schaden.")

BEMAENGELT = {"elemente": [{"element": "Voraussetzung", "status": "korrekt"},
                           {"element": "Begründung", "status": "ungenau",
                            "begruendung": "Der Zusammenhang wird nur vage angesprochen."}],
              "bewertung": "teilweise", "feedback": "Der Zusammenhang zur Wartung bleibt vage.",
              "hinweis": "Vermutlich spielt die Wartung eine Rolle: Sag das bestimmter."}
ANERKANNT = {"elemente": [{"element": "Voraussetzung", "status": "korrekt"},
                          {"element": "Begründung", "status": "korrekt",
                           "begruendung": "Der Fall lässt die Wartung offen, «vermutlich» ist genau."}],
             "bewertung": "korrekt", "feedback": "Richtig, und vorsichtig formuliert, weil der Fall offenlässt, "
                                                 "ob die Wartung vernachlässigt wurde.", "hinweis": ""}


def test_abschwaechungswoerter_und_paarvergleich():
    assert didaktik.abschwaechungen(A) == ["vermutlich"] and didaktik.abschwaechungen(B) == []
    assert didaktik.nur_abschwaechung_verschieden(A, B)
    assert not didaktik.nur_abschwaechung_verschieden(A, A)
    assert not didaktik.nur_abschwaechung_verschieden(A, "Der Hersteller haftet, vermutlich wegen Materialfehler.")
    # fachneutral: Quantenphysik
    assert didaktik.nur_abschwaechung_verschieden(
        "Das Elektron wird wahrscheinlich am Doppelspalt gebeugt, weil es Wellencharakter hat.",
        "Das Elektron wird am Doppelspalt gebeugt, weil es Wellencharakter hat.")


def test_ak3_bemaengelte_vorsicht_bei_offenem_punkt_wird_neu_erzeugt(monkeypatch):
    antworten, prompts = iter([BEMAENGELT, ANERKANNT]), []

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(antworten)), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    r = tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL3, A)
    assert r["bewertung"] == "korrekt"
    assert "Offene Punkte des Sachverhalts" in prompts[0] and "Wartung der Schaukel vernachlässigt" in prompts[0]
    assert "KORREKTUR" in prompts[1] and "vorsichtige Formulierung" in prompts[1]
    assert any("vorsichtige Formulierung" in v for v in r["_verstoesse"])


def test_vorsicht_ohne_offenen_punkt_wird_nicht_beanstandet():
    assert didaktik.vorsicht_bemaengelt(BEMAENGELT, A, []) is None
    assert didaktik.vorsicht_bemaengelt(BEMAENGELT, B, ["ob die Wartung vernachlässigt wurde"]) is None
    assert didaktik.vorsicht_bemaengelt(BEMAENGELT, A, ["ob die Wartung vernachlässigt wurde"])
    assert didaktik.vorsicht_bemaengelt(ANERKANNT, A, ["ob die Wartung vernachlässigt wurde"]) is None


def test_regel_steht_im_benutzerteil_nicht_im_systemprompt(monkeypatch):
    prompts = []
    monkeypatch.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: (prompts.append((s, u)) or
                                                                              (json.dumps(ANERKANNT), {})))
    tutor.evaluate_answer(LESSON, tutor.new_profile(), FALL3, A)
    system, user = prompts[0]
    assert "Vorsichtige Formulierungen" in user and "Vorsichtige Formulierungen" not in system


def test_warnung_bei_gleicher_antwort_mit_anderem_urteil(monkeypatch):
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Vorsicht"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    # Mock: 15-39 Zeichen teilweise, ab 40 korrekt
    c.post(f"/api/session/{sid}/answer", json={"answer": "Vermutlich haftet Anna fahrlässig.", "confidence": 5})
    c.post(f"/api/session/{sid}/wahl", json={"wahl": "ergaenzen"})
    c.post(f"/api/session/{sid}/answer", json={"answer": "Anna haftet, weil sie fahrlässig handelte, Punkt."})
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    assert not [e for e in events if e["type"] == "abschwaechung_warnung"]     # verschiedene Antworten
    sid2 = sid
    monkeypatch.setitem(llm._PROVIDERS, "mock", llm._chat_mock)
    from app import main, store
    s = store.get_session(sid2)
    profil = s["profile"]
    profil.update(wartet_auf="antwort", antworten_aktuell=[{"antwort": A, "bewertung": "teilweise", "hinweis": "",
                                                           "elemente": []}], step=0)
    store.update_session(sid2, profile=profil)
    r = main._antwort_bewerten(sid2, LESSON, profil, profil["current_task"], B, None)
    assert r["bewertung"] == "korrekt"
    w = [e["payload"] for e in store.get_events(sid2) if e["type"] == "abschwaechung_warnung"]
    assert w and w[0]["woerter"] == ["vermutlich"]
