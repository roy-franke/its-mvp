"""D-09: Aufgabe passt zur vorangehenden Theorie."""

import json

from app import didaktik, llm, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())

VERSCHRAENKUNG = {"typ": "theorie", "titel": "Quantenverschränkung", "konzept": "Quantenverschränkung",
                  "inhalt": "Verschränkte Teilchen bleiben über grosse Distanzen miteinander verbunden.",
                  "beispiel": "Zwei Handschuhe in getrennten Paketen."}
FAMILIENHAUPT = {"typ": "theorie", "titel": "Haftung des Familienhaupts", "konzept": "Familienhauptshaftung",
                 "inhalt": "Das Familienhaupt haftet nach Art. 333 ZGB für Schäden, die unmündige Hausgenossen "
                           "verursachen, wenn es die übliche Sorgfalt in der Beaufsichtigung nicht beweist.",
                 "beispiel": "Ein Kind wirft einen Stein in die Scheibe des Nachbarn."}


def _aufgabe(konzept, **mehr):
    return {"titel": "Fall", "inhalt": "Ein Baum stürzt auf ein Auto.", "frage": "Wer muss bezahlen, und warum?",
            "aufgabentyp": "anwenden", "optionen": [], "erwartete_antwort": "Die verantwortliche Person haftet.",
            "schluesselbegriffe": [], "erwartete_elemente": ["verantwortliche Person", "Begründung"],
            "konzept": konzept, **mehr}


def test_ak1_abweichendes_konzept_loest_verstoss_und_korrektur_aus(monkeypatch):
    antworten = iter([_aufgabe("Unschärferelation"), _aufgabe("Quantenverschränkung")])
    prompts = []

    def p(system, user, json_mode=False):
        prompts.append(user)
        return json.dumps(next(antworten), ensure_ascii=False), {}
    monkeypatch.setitem(llm._PROVIDERS, "mock", p)
    profil = dict(tutor.new_profile(), last_type="theorie", level="intermediate",
                  covered=["Quantenverschränkung", "Unschärferelation"])
    history = [{"type": "task", "payload": VERSCHRAENKUNG, "created_at": 0, "id": 1}]
    aufgabe = tutor.generate_task(dict(LESSON, einstellungen={"einsatzart": "vertiefung"}), profil, history)
    assert aufgabe["konzept"] == "Quantenverschränkung"
    assert "KORREKTUR" in prompts[1] and "«Quantenverschränkung»" in prompts[1]
    assert any("vorangehende Theorie" in v for v in aufgabe["_verstoesse"])
    # Die Theorie steht im Benutzerteil, mit genau ihrem Konzept (nicht covered[-1])
    assert "UNMITTELBAR VORANGEHENDE THEORIE" in prompts[0] and "Konzept: Quantenverschränkung" in prompts[0]
    assert "Unschärferelation' als Theorie" not in prompts[0]


def test_ak2_unterthema_in_der_theorie_oberthema_in_der_aufgabe():
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Kausalhaftung"), FAMILIENHAUPT)
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Haftung"), dict(FAMILIENHAUPT, konzept="Tierhalterhaftung"))
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Kausalhaftung"),
                                              dict(FAMILIENHAUPT, konzept="Kausalhaftung ohne Verschulden"))


def test_gleiches_oder_spezifischeres_konzept_ist_kein_verstoss():
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Familienhauptshaftung"), FAMILIENHAUPT) is None
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Haftung des Familienhaupts"),
                                              dict(FAMILIENHAUPT, konzept="Familienhaupt")) is None
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Kausal-Haftung"), dict(FAMILIENHAUPT, konzept="Kausalhaftung")) is None
    assert didaktik.aufgabe_passt_zur_theorie(_aufgabe("Tierhalterhaftungen"),
                                              dict(FAMILIENHAUPT, konzept="Tierhalterhaftung")) is None


def test_begriffspruefung_nur_bei_klaren_faellen():
    texte = didaktik.theorietext(FAMILIENHAUPT)
    klar = _aufgabe("Familienhauptshaftung", schluesselbegriffe=["Tierhalterhaftung"])
    assert "Tierhalterhaftung" in (didaktik.begriff_nicht_erklaert(klar, texte, LESSON) or "")
    # Beschreibungen, Begriffe aus der Theorie oder Wörter ausserhalb der Lektion: kein Verstoss
    for b in (["die Sorgfalt in der Beaufsichtigung beweisen"], ["Familienhaupt"], ["Velohelm"]):
        assert didaktik.begriff_nicht_erklaert(_aufgabe("x", schluesselbegriffe=b), texte, LESSON) is None, b
