"""D-06: Material mit den Lernzielen abgleichen."""

import json

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)
QUANTEN = json.loads(open("app/lessons/einfuhrung-in-die-quantenphysik.json", encoding="utf-8").read())

VOLLSTAENDIG_ZIELE = ["Die Tierhalterhaftung erklären", "Die Werkeigentümerhaftung anwenden"]
VOLLSTAENDIG = (
    "Die Tierhalterhaftung nach Art. 56 OR macht die Halterin eines Tieres für Schäden haftbar, "
    "die das Tier verursacht, auch ohne eigenes Verschulden. Das ist so, weil wer ein Tier hält, "
    "eine Gefahrenquelle schafft und daraus Nutzen zieht. Zum Beispiel haftet die Halterin, wenn "
    "ihr Hund einen Velofahrer zu Fall bringt. Entlasten kann sie sich nur, wenn sie beweist, dass "
    "sie alle gebotene Sorgfalt angewendet hat.\n\n"
    "Die Werkeigentümerhaftung nach Art. 58 OR trifft den Eigentümer eines Gebäudes oder Werks, "
    "wenn ein Schaden durch fehlerhafte Anlage oder mangelhaften Unterhalt entsteht. Sie gilt, weil "
    "der Eigentümer das Werk kontrolliert und deshalb für dessen Sicherheit verantwortlich ist. Zum "
    "Beispiel haftet der Hauseigentümer, wenn ein loser Dachziegel auf ein parkiertes Auto fällt. "
    "Anwenden heisst: prüfen, ob ein Werk vorliegt, ob es mangelhaft war und ob der Mangel den "
    "Schaden verursacht hat. Diese Prüfung ist wichtig, denn fehlt einer der Punkte, entfällt die Haftung. "
) * 2


def test_quantenmaterial_meldet_luecken():
    r = c.post("/api/teacher/lessons/check-material",
               json={"lernziele": QUANTEN["lernziele"], "material": QUANTEN["material"]}).json()
    assert r["luecken"] >= 1
    assert r["hinweise"] and "sehr kurz" in r["hinweise"][0]
    assert len(r["ziele"]) == len(QUANTEN["lernziele"])
    assert any(z["beispiel"] is False for z in r["ziele"])


def test_vollstaendiges_material_ohne_luecken():
    r = c.post("/api/teacher/lessons/check-material",
               json={"lernziele": VOLLSTAENDIG_ZIELE, "material": VOLLSTAENDIG}).json()
    assert r["luecken"] == 0 and r["geprueft"]
    assert all(z["erklaerung"] and z["beispiel"] and z["begruendung"] for z in r["ziele"])


def test_pruefung_verlangt_ziele_und_material():
    assert c.post("/api/teacher/lessons/check-material",
                  json={"lernziele": [], "material": VOLLSTAENDIG}).status_code == 400
    assert c.post("/api/teacher/lessons/check-material",
                  json={"lernziele": ["x"], "material": ""}).status_code == 400
