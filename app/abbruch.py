"""T-28: Die Bearbeitung einer Anfrage stoppen.

Die Oberfläche schickt bei allem, was die lernende Person als Text an den
Tutor sendet (Antwort, Verständnisfrage, «Theorie dazu», «Genauer erklären»,
Einwand, Einstufung), eine Anfrage-ID im Header X-ITS-Anfrage mit. «Stoppen»
ruft POST /api/session/{sid}/stopp mit dieser ID auf (Entscheid E8).

Der Server merkt sich den Stopp und
- bricht bei Ollama die laufende Generierung ab (Streaming, Verbindung zu),
  damit die nächste Anfrage nicht hinter der alten wartet,
- startet keinen weiteren LLM-Aufruf dieser Anfrage mehr,
- verwirft ein Ergebnis, das trotzdem noch eintrifft, bevor es Profil, Zählung
  oder Verlauf verändert (`uebernehmen` an den Übernahmestellen in main.py).

Kommt der Stopp erst, nachdem das Ergebnis übernommen ist, meldet der Server
«zu_spaet»; die Oberfläche zeigt die Antwort dann normal an.

Die Liste der Anfragen liegt im Arbeitsspeicher. Das genügt, weil eine
Anfrage nur so lange stoppbar ist, wie sie läuft (ein Serverprozess).
"""

import contextvars
import re
import threading
import time

HEADER = "X-ITS-Anfrage"
_GUELTIG = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
AUFBEWAHREN = 15 * 60


class Abgebrochen(Exception):
    """Die Anfrage wurde gestoppt; trägt sid, Art, Text und Profil-Stand mit."""

    def __init__(self, info: dict | None = None):
        super().__init__("Bearbeitung gestoppt")
        self.info = info or {}


_lock = threading.Lock()
_anfragen: dict[str, dict] = {}
_aktuell: contextvars.ContextVar = contextvars.ContextVar("anfrage", default=None)


def _aufraeumen(jetzt: float) -> None:
    for aid in [a for a, e in _anfragen.items() if jetzt - e["zeit"] > AUFBEWAHREN]:
        del _anfragen[aid]


def beginnen(anfrage_id: str | None, sid: str, art: str, text: str = "", profil: dict | None = None) -> None:
    """Meldet eine stoppbare Anfrage an (ohne gültige ID: nicht stoppbar).

    `profil` ist der Stand vor der Anfrage; er wird nach einem Stopp
    zurückgeschrieben, falls die Anfrage schon vorher etwas gespeichert hat.
    """
    if not anfrage_id or not _GUELTIG.match(anfrage_id):
        _aktuell.set(None)
        return
    jetzt = time.time()
    with _lock:
        _aufraeumen(jetzt)
        e = _anfragen.get(anfrage_id)
        if e is None or e["sid"] != sid:
            e = {"sid": sid, "status": "laufend", "signal": threading.Event(), "schliessen": None}
            _anfragen[anfrage_id] = e
        e.update(zeit=jetzt, art=art, text=text[:1000], profil=profil)
        vorab = e["status"] == "abgebrochen"
    _aktuell.set(anfrage_id)
    if vorab:                      # Stopp kam an, bevor die Anfrage lief
        raise Abgebrochen(info())


def info() -> dict:
    aid = _aktuell.get()
    e = _anfragen.get(aid) if aid else None
    if not e:
        return {}
    return {"anfrage": aid, "sid": e["sid"], "art": e.get("art"), "text": e.get("text", ""),
            "profil": e.get("profil")}


def stoppen(sid: str, anfrage_id: str) -> str:
    """«abgebrochen», «zu_spaet» oder «unbekannt»."""
    if not anfrage_id or not _GUELTIG.match(anfrage_id):
        return "unbekannt"
    with _lock:
        e = _anfragen.get(anfrage_id)
        if e is None:
            # Der Stopp ist schneller als die Anfrage selbst: vormerken
            _anfragen[anfrage_id] = {"sid": sid, "status": "abgebrochen", "signal": threading.Event(),
                                     "schliessen": None, "zeit": time.time()}
            _anfragen[anfrage_id]["signal"].set()
            return "abgebrochen"
        if e["sid"] != sid:
            return "unbekannt"
        if e["status"] == "uebernommen":
            return "zu_spaet"
        e["status"] = "abgebrochen"
        e["signal"].set()
        schliessen = e.get("schliessen")
    if schliessen:
        try:
            schliessen()           # laufende Verbindung zu Ollama schliessen
        except Exception:          # schon geschlossen
            pass
    return "abgebrochen"


def signal() -> threading.Event | None:
    """Ereignis der laufenden Anfrage, None wenn sie nicht stoppbar ist."""
    aid = _aktuell.get()
    e = _anfragen.get(aid) if aid else None
    return e["signal"] if e else None


def gestoppt() -> bool:
    s = signal()
    return bool(s and s.is_set())


def pruefen() -> None:
    """Vor jedem LLM-Aufruf: nach einem Stopp keinen weiteren starten."""
    if gestoppt():
        raise Abgebrochen(info())


def schliessen_merken(fn) -> None:
    """Merkt sich, wie eine laufende Verbindung geschlossen wird (oder None)."""
    aid = _aktuell.get()
    if not aid:
        return
    with _lock:
        if aid in _anfragen:
            _anfragen[aid]["schliessen"] = fn


def uebernehmen() -> None:
    """Übernahmestelle: Nach einem Stopp wird das Ergebnis verworfen, sonst gilt
    die Anfrage ab jetzt als übernommen (ein späterer Stopp kommt zu spät)."""
    aid = _aktuell.get()
    if not aid:
        return
    with _lock:
        e = _anfragen.get(aid)
        if e and e["status"] == "abgebrochen":
            abgebrochen = True
        else:
            abgebrochen = False
            if e:
                e["status"] = "uebernommen"
                e["schliessen"] = None
    if abgebrochen:
        raise Abgebrochen(info())


def zuruecksetzen() -> None:
    """Für Tests."""
    with _lock:
        _anfragen.clear()
    _aktuell.set(None)
