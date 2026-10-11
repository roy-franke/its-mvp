"""T-13: Formatierung der Tutor-Texte (serverseitige Teile)."""

import json
from pathlib import Path

from app import didaktik, tutor

LESSON = json.loads(open("app/lessons/haftungsrecht.json", encoding="utf-8").read())
QUANTEN_ALT = ("Grundlagen und EinstiegFür den Einstieg in die Welt der Quanten sind folgende Kernkonzepte "
               "wichtig:Welle-Teilchen-Dualismus: Licht und Materie zeigen sowohl Wellen- als auch "
               "Teilstrukturen.Superposition: Teilchen können sich in einer Überlagerung mehrerer Zustände "
               "befinden.Heisenbergsche Unschärferelation: Ort und Impuls sind nicht gleichzeitig exakt "
               "messbar.Quantenverschränkung: Teilchen bleiben über grosse Distanzen miteinander verbunden.")


def test_ak4_ursache_material_ohne_zeilenumbrueche_wird_erkannt():
    assert didaktik.verklebte_stellen(QUANTEN_ALT) == ["EinstiegFür", "wichtig:Welle", "Teilstrukturen.Superposition"]
    for datei in Path("app/lessons").glob("*.json"):
        material = json.loads(datei.read_text(encoding="utf-8"))["material"]
        assert didaktik.verklebte_stellen(material) == [], datei.name


def test_saetze_trennen_laesst_abkuerzungen_stehen():
    assert didaktik.saetze_trennen("exakt messbar.Quantenverschränkung") == "exakt messbar. Quantenverschränkung"
    assert didaktik.saetze_trennen("z.B. Art. 41 OR, d.h. Haftung") == "z.B. Art. 41 OR, d.h. Haftung"


def test_materialpruefung_meldet_verklebten_text():
    r = tutor.check_material(["Superposition erklären"], QUANTEN_ALT)
    assert any("Zeilenumbrüche" in h and "EinstiegFür" in h for h in r["hinweise"])


def test_quantenmaterial_ist_gegliedert():
    material = json.loads(Path("app/lessons/einfuhrung-in-die-quantenphysik.json").read_text(encoding="utf-8"))["material"]
    assert material.startswith("### Grundlagen und Einstieg\n\n")
    assert material.count("\n- ") == 4


def test_systemprompt_verlangt_markdown_teilmenge_einmal_fuer_alle_schritte():
    s = tutor._system_prompt(LESSON)
    assert "«- »" in s and "«### »" in s and "Keine Links, Bilder, Tabellen oder HTML" in s


def test_formatjs_wird_von_beiden_seiten_eingebunden():
    for seite in ("static/index.html", "static/teacher.html"):
        assert '<script src="/static/format.js"></script>' in Path(seite).read_text(encoding="utf-8")
    js = Path("static/format.js").read_text(encoding="utf-8")
    # zuerst maskieren, dann formatieren; keine Bibliothek vom CDN
    assert "maskiere(text)" in js and "cdn" not in js.lower()
