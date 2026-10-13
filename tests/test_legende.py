"""T-25: Die Legende kennt jede Wahl, die der Server anbieten kann.

Die Oberfläche selbst prüft tests/ui/ui_checks.py (Szenario t25 und die
Legendenprüfung in allen Szenarien). Hier wird nur sichergestellt, dass die
Zuordnung in index.html keine Wahl-ID des Servers vergisst.
"""

import re
from pathlib import Path

from app import tutor

INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


def _legende_ids() -> set[str]:
    s = INDEX.read_text(encoding="utf-8")
    block = s[s.index("const LEGENDE_WAHL = {"):s.index("const LEGENDE_WEITER")]
    return set(re.findall(r"^\s+(\w+):", block, re.MULTILINE))


def test_jede_wahl_des_servers_hat_einen_legendentext():
    ids = {w for art in tutor.WAHL_FALLBACK.values() for w, _ in art}
    ids |= {w["id"] for w in tutor.wahl_nach_bewertungsfehler({"erwartete_antwort": "x"}, 2)}
    ids |= {w["id"] for w in tutor.wahl_nach_bewertungsfehler({}, 1)}
    ids |= {w["id"] for w in tutor.wahl_nach_teilweise({"erwartete_antwort": "x"}, 0)}
    assert ids <= _legende_ids(), ids - _legende_ids()


def test_legende_wird_von_jeder_modusfunktion_aktualisiert():
    s = INDEX.read_text(encoding="utf-8")
    for fn in ("setAnswerMode", "setRetryMode", "setTheoryMode", "setContinueMode", "setWaitMode", "renderWahl"):
        rumpf = s[s.index(f"function {fn}("):]
        rumpf = rumpf[:rumpf.index("\n}\n")]
        assert "aktualisiereLegende()" in rumpf or "setAnswerMode(" in rumpf or "wahlEntfernen()" in rumpf, fn
