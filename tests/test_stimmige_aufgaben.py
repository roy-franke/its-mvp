"""D-13: Fall, Titel und Musterlösung stimmen überein (Auftrag 3).

Die Fälle stammen aus dem Feedback vom 13.10.2026 (Anhang B).
"""

import json

from fastapi.testclient import TestClient

from app import didaktik, llm, tutor
from app.main import app

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
# Vertiefung: Aufgaben dürfen Unerklärtes voraussetzen, die Zählung der Aufrufe bleibt übersichtlich
VERTIEFUNG = dict(LESSON, einstellungen={"einsatzart": "vertiefung"})

THEORIE_TIER = {
    "typ": "theorie", "titel": "Tierhalterhaftung", "konzept": "Tierhalterhaftung",
    "inhalt": "Wer ein Tier hält, haftet für den Schaden, den es anrichtet, auch ohne eigenes Verschulden "
              "(Art. 56 OR). Die Halterin kann sich nur entlasten, wenn sie alle gebotene Sorgfalt beweist.",
    "beispiel": "Beisst ein Hund einen Passanten, haftet die Halterin, auch ohne eigenes Verschulden.",
    "merkmale": ["Tier", "Halter"],
}

# Fall 2 aus Anhang B: Titel nennt die Tierhalterhaftung, der Fall enthält kein Tier
BALL = {
    "titel": "Tierhalterhaftung im Alltag",
    "inhalt": "Ein Junge spielt mit einem Ball im Park. Der Ball rollt in einen Zaun und zerbricht eine "
              "Fensterscheibe eines nahegelegenen Hauses. Der Besitzer des Hauses will Schadenersatz von dem "
              "Jungen verlangen.",
    "frage": "Wer ist verantwortlich für den Schaden und welche Art der Haftung greift hier?",
    "aufgabentyp": "anwenden", "optionen": [],
    "erwartete_antwort": "Der Halter haftet nach Art. 56 OR, eine Kausalhaftung.",
    "schluesselbegriffe": [], "konzept": "Tierhalterhaftung",
    "erwartete_elemente": ["verantwortliche Person", "Art der Haftung"],
    "merkmale": [],
}

KATZE = dict(BALL, titel="Ärger im Treppenhaus",
             inhalt="Die Katze von Frau Rossi schleicht ins Treppenhaus und wirft eine teure Vase der Nachbarin "
                    "um. Frau Rossi hat die Wohnungstür offen gelassen.",
             frage="Wer haftet für die Vase und welche Art der Haftung greift?",
             merkmale=[{"merkmal": "Tier", "im_fall": "Die Katze"}, {"merkmal": "Halter", "im_fall": "Frau Rossi"}],
             erwartete_antwort="Frau Rossi als Halterin der Katze haftet nach Art. 56 OR, eine Kausalhaftung.")


def _profil_nach_theorie():
    return dict(tutor.new_profile(), level="intermediate", last_type="theorie",
                covered=["Tierhalterhaftung"], erklaert=["Tierhalterhaftung"])


def test_ak1_fall_ohne_merkmal_loest_neugenerierung_aus(monkeypatch):
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    antworten = iter([BALL, KATZE])
    prompts = []

    def provider(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(antworten)), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    t = tutor.generate_task(LESSON, _profil_nach_theorie(), [{"type": "task", "payload": THEORIE_TIER}])
    assert t["titel"] == "Ärger im Treppenhaus"
    assert any("prägende Merkmal" in v and "«Tier»" in v for v in t["_verstoesse"])
    assert "KORREKTUR" in prompts[1] and "Tier" in prompts[1]


def test_merkmal_mit_fundstelle_im_fall_genuegt():
    assert didaktik.merkmale_fehlen_im_fall(KATZE, THEORIE_TIER) is None
    erfunden = dict(KATZE, merkmale=[{"merkmal": "Tier", "im_fall": "der Hund"}, {"merkmal": "Halter", "im_fall": "x"}])
    assert "«Tier»" in didaktik.merkmale_fehlen_im_fall(erfunden, THEORIE_TIER)
    assert didaktik.merkmale_fehlen_im_fall(dict(BALL, merkmale=[]), None) is None      # alte Aufgaben


def test_ak2_titel_mit_loesungsbegriff_wird_beanstandet():
    task = {"titel": "Kausalhaftung beim Spielplatz",
            "inhalt": "Ein Kind spielt auf einem Spielplatz. Während des Spiels bricht eine Schaukel ab und das "
                      "Kind verletzt sich. Der Spielplatz wird von einer Stadtverwaltung betrieben.",
            "frage": "Wer ist für den Schaden verantwortlich und welche Art der Haftung greift hier?",
            "erwartete_antwort": "Die Stadt als Werkeigentümerin, eine Kausalhaftung.",
            "schluesselbegriffe": ["Kausalhaftung"], "konzept": "Werkeigentümerhaftung"}
    fach = didaktik.fachvokabular(LESSON)
    v = didaktik.loesungswort_in_titel(task, fach)
    assert v and "Kausalhaftung" in v and "neutralen Titel" in v
    assert didaktik.loesungswort_in_titel(dict(task, titel="Unfall auf dem Spielplatz"), fach) is None
    # auch ohne Schlüsselbegriff, wenn die erwartete Antwort das Konzept verlangt
    ohne = dict(task, titel="Werkeigentümerhaftung auf dem Spielplatz", schluesselbegriffe=[],
                erwartete_antwort="Die Stadt haftet aus Werkeigentümerhaftung.")
    assert didaktik.loesungswort_in_titel(ohne, fach)


def test_ak3_abweichende_gegenpruefung_wird_unsicher_und_hinterlegt(monkeypatch):
    monkeypatch.setenv("ITS_MOCK_GEGENPRUEFUNG", "abweichend")
    gesehen = []
    original = llm._PROVIDERS["mock"]

    def spy(system, user, json_mode=False):
        gesehen.append(llm._label(user))
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    t = tutor.generate_task(VERTIEFUNG, dict(tutor.new_profile(), level="advanced"), [])
    mp = t["musterloesung_pruefung"]
    assert mp["ergebnis"] == "unsicher"
    assert "Anna muss nicht zahlen" in t["alternative_loesungen"][0]
    assert gesehen.count("NAECHSTE_AUFGABE") == 2             # einmal neu erzeugt
    assert gesehen.count("MUSTERLOESUNG_PRUEFEN") == 2
    assert mp["offene_punkte"] and mp["verworfene_aufgabe"]["titel"]
    # Die Musterlösung selbst sieht die Gegenprüfung nicht
    assert "musterloesung_pruefung" not in tutor.fuer_lernende(t)


def test_gegenpruefung_kennt_die_musterloesung_nicht(monkeypatch):
    prompts = {}
    original = llm._PROVIDERS["mock"]

    def spy(system, user, json_mode=False):
        prompts.setdefault(llm._label(user), user)
        return original(system, user, json_mode)
    monkeypatch.setitem(llm._PROVIDERS, "mock", spy)
    t = tutor.generate_task(LESSON, dict(tutor.new_profile(), level="advanced"), [])
    assert t["musterloesung_pruefung"]["ergebnis"] == "uebereinstimmend"
    assert t["erwartete_antwort"] not in prompts["MUSTERLOESUNG_PRUEFEN"]
    assert "MUSTERLOESUNG_VERGLEICHEN" not in prompts        # Fachbegriffe stimmen, kein zweiter Aufruf


def test_nach_neugenerierung_uebereinstimmend(monkeypatch):
    aufgaben = iter([
        BALL | {"titel": "Glasbruch im Park", "konzept": "Verschuldenshaftung",
                "erwartete_antwort": "Der Junge haftet nach Art. 41 OR, Verschuldenshaftung."},
        BALL | {"titel": "Glasbruch im Park", "konzept": "Verschuldenshaftung",
                "inhalt": BALL["inhalt"] + " Der Junge ist 15 Jahre alt und urteilsfähig.",
                "erwartete_antwort": "Der urteilsfähige Junge haftet selbst, Verschuldenshaftung."}])
    loesungen = iter([
        {"loesung": "Die Eltern haften aus Familienhauptshaftung.", "offene_punkte": ["Alter des Jungen"]},
        {"loesung": "Der urteilsfähige Junge haftet selbst, Verschuldenshaftung.", "offene_punkte": []}])

    def provider(system, user, json_mode=False):
        label = llm._label(user)
        if label == "NAECHSTE_AUFGABE":
            return json.dumps(next(aufgaben)), {}
        if label == "MUSTERLOESUNG_PRUEFEN":
            return json.dumps(next(loesungen)), {}
        return json.dumps({"uebereinstimmend": False, "unterschied": "B nennt die Eltern"}), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", provider)
    t = tutor.generate_task(VERTIEFUNG, dict(tutor.new_profile(), level="advanced"), [])
    mp = t["musterloesung_pruefung"]
    assert mp["ergebnis"] == "nach_neugenerierung", mp
    assert "urteilsfähig" in t["inhalt"] and mp["erste_pruefung"]["unterschied"] == "B nennt die Eltern"


def test_abschaltbar(monkeypatch):
    monkeypatch.setenv("ITS_MUSTERLOESUNG_PRUEFEN", "false")
    assert "musterloesung_pruefung" not in tutor.generate_task(LESSON, tutor.new_profile(), [])


def test_ak3_ereignis_im_lernverlauf(monkeypatch):
    monkeypatch.setenv("ITS_MOCK_GEGENPRUEFUNG", "abweichend")
    c = TestClient(app)
    c.post("/api/learner/login", json={"name": "Gegenprobe"})
    sid = c.post("/api/session/start", json={"lesson_id": "haftungsrecht"}).json()["session_id"]
    c.post(f"/api/session/{sid}/assess", json={"answers": ["a", "b", "c"]})
    for _ in range(3):
        if c.post(f"/api/session/{sid}/next").json()["task"]["typ"] == "aufgabe":
            break
    events = c.get(f"/api/teacher/sessions/{sid}").json()["events"]
    ev = [e["payload"] for e in events if e["type"] == "musterloesung_geprueft"]
    assert ev and ev[-1]["ergebnis"] == "unsicher" and ev[-1]["alternative_loesungen"]
    html = open("static/teacher.html", encoding="utf-8").read()
    assert 'ev.type === "musterloesung_geprueft"' in html and "MUSTERLOESUNG_PRUEFEN" in html


def test_ak5_merkmale_landen_nicht_auf_der_verbotsliste():
    """Ursache Fall 2: Mit «Hund» auf der Liste und der Anweisung «und verwandte Wörter» mied das
    Modell Tiere ganz. Das Merkmal «Tier» steht nie auf der Liste, die Anweisung verlangt es ausdrücklich."""
    theorie = dict(THEORIE_TIER, inhalt="Halterinnen haften ohne eigenes Verschulden (Art. 56 OR).",
                   beispiel="Das Tier der Nachbarin, ein Hund, beisst einen Passanten.")
    woerter = didaktik.fallwoerter(theorie)
    assert "Hund" in woerter and "Tier" not in woerter
    prompts = []
    original = llm._PROVIDERS["mock"]
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setitem(llm._PROVIDERS, "mock", lambda s, u, json_mode=False: prompts.append(u) or original(s, u))
    try:
        tutor.generate_task(LESSON, _profil_nach_theorie(), [{"type": "task", "payload": theorie}])
    finally:
        mp.undo()
    aufgabe = next(p for p in prompts if p.startswith("AUFGABE: NAECHSTE_AUFGABE"))
    assert "verwandte Wörter" not in aufgabe
    assert "MUSS die Merkmale des Konzepts enthalten" in aufgabe and "Tier, Halter" in aufgabe


def test_theorie_liefert_merkmale():
    t = tutor.generate_theory(LESSON, tutor.new_profile(), [])
    assert t["merkmale"] == ["Schaden"]
