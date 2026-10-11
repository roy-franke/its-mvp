"""T-15/T-16: Eindeutige Beschriftungen in der Oberfläche."""

import re
from pathlib import Path

SEITEN = sorted(Path("static").glob("*.html"))


def test_ak2_kein_dialogbutton_heisst_abbrechen():
    """Der Button zum Zurückkehren heisst nie «Abbrechen» (auch nicht in Skripten)."""
    for seite in SEITEN:
        text = seite.read_text(encoding="utf-8")
        assert not re.search(r">\s*Abbrechen\s*<", text), seite.name
        assert not re.search(r"""["'`]Abbrechen["'`]""", text), seite.name


def test_ak1_abbrechen_dialog_mit_neuen_beschriftungen():
    text = Path("static/index.html").read_text(encoding="utf-8")
    assert '"Ja, Lektion abbrechen"' in text and '"Nein, weiterlernen"' in text
    assert '"Ja, neu beginnen"' in text and '"Zurück zur Übersicht"' in text


def test_folgenreiche_handlung_rot_umrandet():
    index = Path("static/index.html").read_text(encoding="utf-8")
    assert '<button id="modal-ok" class="danger">' in index
    lektionen = Path("static/lessons.html").read_text(encoding="utf-8")
    assert '<button class="danger" id="modal-ok">Ja, Lektion archivieren</button>' in lektionen


def test_t16_niveau_dropdown_ohne_festhalten():
    text = Path("static/index.html").read_text(encoding="utf-8")
    auswahl = text[text.index('<select id="level-control"'):text.index("</select>", text.index('<select id="level-control"'))]
    assert "festhalten" not in auswahl
    for label in ("Automatisch (empfohlen)", ">Grundlagen<", ">Fortgeschritten<", ">Vertieft<"):
        assert label in auswahl
    assert "bis du wieder «Automatisch» wählst" in text
