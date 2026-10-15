"""T-30: Lernmaterialien aus der Vektordatenbank im Tutor verwenden (RAG).

Ablauf pro LLM-Aufruf mit Lektionsmaterial (tutor._chat):

1. Modus (`modus`): «rag» oder «voll». RAG gilt, wenn die Lektion Material
   aus der Ablage verwendet, die Vektordatenbank eingerichtet und erreichbar
   ist, alle Materialien mit dem aktuellen Modell indexiert sind und die
   Einstellung der Lektion es will: «automatisch» ab ITS_RAG_AB_TOKENS
   (Standard 4000 geschätzte Tokens), «auszuege» immer, «ganz» nie
   (Entscheid E5). Sonst arbeitet der Tutor wie bisher mit dem ganzen Material.
2. Retrieval (`auszuege`): pro Schrittart eine oder mehrere Abfragen
   (Konzept, Lernziele, Aufgabe, Antwort, Frage). Die Treffer werden
   reihum zusammengeführt, damit jede Abfrage mindestens einen Auszug
   beiträgt, bis ITS_RAG_K Auszüge oder ITS_RAG_MAX_ZEICHEN erreicht sind.
3. Augment: Die Auszüge stehen nummeriert am Ende des Benutzerteils. Der
   Systemprompt nennt statt des ganzen Materials nur die Quellen und bleibt
   pro Lektion gleich (Prompt-Cache, HANDOVER Abschnitt 4b).
4. Generate: Das Modell nennt im Feld «auszuege» die Nummern, auf die es sich
   stützt. Der Code macht daraus Fundstellen mit Seite und Abschnitt
   (nie eine Angabe, die es nicht gibt, vgl. N-01).

Jede Abfrage wird gesammelt (`abrufe_holen`) und von main.py als Ereignis
`rag_abruf` in den Lernverlauf geschrieben.
"""

import contextvars
import logging
import os
import time

from . import einstellungen, llm, materialien, vektoren

log = logging.getLogger("its.rag")

_abrufe: contextvars.ContextVar = contextvars.ContextVar("rag_abrufe", default=None)
ABSCHNITT_KOPF = "AUSZÜGE AUS DEM MATERIAL"


def schwelle() -> int:
    return int(os.getenv("ITS_RAG_AB_TOKENS", "4000"))


def k() -> int:
    return max(1, int(os.getenv("ITS_RAG_K", "6")))


def max_zeichen() -> int:
    return max(500, int(os.getenv("ITS_RAG_MAX_ZEICHEN", "7000")))


def global_aus() -> bool:
    return (os.getenv("ITS_RAG") or "auto").strip().lower() in ("aus", "off", "false", "0", "nein")


# ---------------------------------------------------------------- Protokoll

def sammeln_beginnen() -> None:
    """Pro Anfrage eine neue Liste (Middleware in main.py)."""
    _abrufe.set([])


def protokoll(info: dict) -> None:
    liste = _abrufe.get()
    if liste is not None:
        liste.append(info)


def abrufe_holen() -> list[dict]:
    liste = _abrufe.get()
    if not liste:
        return []
    out = list(liste)
    liste.clear()
    return out


# ---------------------------------------------------------------- Modus

def _ids(lesson: dict) -> list[str]:
    return [m for m in lesson.get("materialien") or [] if isinstance(m, str)]


def modus(lesson: dict) -> tuple[str, str]:
    """("rag" | "voll", Grund)."""
    wahl = einstellungen.settings(lesson)["materialzugriff"]
    ids = _ids(lesson)
    if global_aus():
        return "voll", "RAG auf dem Server ausgeschaltet (ITS_RAG)"
    if wahl == "ganz":
        return "voll", "Einstellung der Lektion: ganzes Material"
    if not ids:
        return "voll", "keine Lernmaterialien aus der Ablage"
    if not vektoren.aktiv():
        return "voll", "keine Vektordatenbank eingerichtet"
    tokens = llm.schaetze_tokens(lesson.get("material") or "")
    if wahl == "automatisch" and tokens < schwelle():
        return "voll", f"Material klein genug ({tokens} von {schwelle()} Tokens)"
    for mid in ids:
        m = materialien.holen(mid)
        stand = vektoren.index_stand(m) if m else "fehlt"
        if m and stand == "ohne_text":
            continue
        if stand != "bereit":
            return "voll", f"Lernmaterial «{(m or {}).get('name', mid)}» ist nicht indexiert ({stand})"
    if not vektoren.erreichbar():
        return "voll", "Vektordatenbank nicht erreichbar"
    return "rag", f"Auszüge aus der Vektordatenbank ({tokens} Tokens Material)"


def _quellname(lesson: dict, material_id: str, standard: str) -> str:
    """Name des Materials, wie er in der Lektion steht («Skript (2)» bei gleichen Namen)."""
    for q in lesson.get("quellen") or []:
        if isinstance(q, dict) and q.get("material_id") == material_id:
            return q.get("name") or standard
    return standard


def uebersicht(lesson: dict) -> str:
    """Materialteil des Systemprompts im RAG-Modus (konstant pro Lektion)."""
    zeilen = []
    for mid in _ids(lesson):
        m = materialien.holen(mid) or {}
        teile = [m.get("dateiname", "")]
        if m.get("seiten"):
            teile.append(f"{m['seiten']} Seiten")
        zeile = f"- «{_quellname(lesson, mid, m.get('name', mid))}» ({', '.join(t for t in teile if t)})"
        if m.get("beschreibung"):
            zeile += f": {m['beschreibung']}"
        zeilen.append(zeile)
    eigen = (lesson.get("material_eigen") or "").strip()
    return ("MATERIAL: Das Lektionsmaterial liegt in einer Vektordatenbank und besteht aus diesen Quellen:\n"
            + "\n".join(zeilen) + "\n"
            f"Zu jeder Anfrage erhältst du am Ende unter «{ABSCHNITT_KOPF}» nummerierte Abschnitte, die zur "
            "Anfrage passen. Sie sind für diese Anfrage dein Lektionsmaterial: Was weder in den Auszügen noch "
            "im eigenen Text der Lehrperson steht, behandelst du so, als stünde es nicht im Material. Gib im "
            "JSON-Objekt zusätzlich das Feld \"auszuege\" an, eine Liste mit den Nummern der Auszüge, auf die "
            "du dich stützt, zum Beispiel [1, 3]; stützt du dich auf keinen, eine leere Liste."
            + (f"\n\nEIGENER TEXT DER LEHRPERSON:\n{eigen}" if eigen else ""))


# ---------------------------------------------------------------- Retrieval

def fundstelle(t: dict) -> str:
    """«S. 3, Art. 41» aus Seite und Abschnitt eines Treffers."""
    teile = []
    von, bis = t.get("seite_von"), t.get("seite_bis")
    if von:
        teile.append(f"S. {von}" if not bis or bis == von else f"S. {von}–{bis}")
    if t.get("abschnitt"):
        teile.append(str(t["abschnitt"])[:80])
    return ", ".join(teile)


def suchen(ids: list[str], anfragen: list[str], anzahl: int | None = None,
           zeichen: int | None = None) -> list[dict]:
    """Treffer aller Abfragen, reihum zusammengeführt, ohne Doppelte."""
    anzahl, zeichen = anzahl or k(), zeichen or max_zeichen()
    anfragen = [a.strip()[:1500] for a in anfragen if a and a.strip()]
    if not anfragen:
        return []
    listen = [vektoren.suchen(a, ids, anzahl) for a in anfragen]
    out, gesehen, summe = [], set(), 0
    for runde in range(anzahl):
        for liste in listen:
            if runde < len(liste) and liste[runde]["id"] not in gesehen:
                t = liste[runde]
                if out and summe + len(t["text"]) > zeichen:
                    continue
                gesehen.add(t["id"])
                out.append(t)
                summe += len(t["text"])
                if len(out) >= anzahl:
                    return out
    return out


def auszuege(lesson: dict, anfragen: list[str], schrittart: str) -> tuple[str, dict]:
    """Text für den Benutzerteil und Protokoll des Abrufs."""
    t0 = time.time()
    treffer = suchen(_ids(lesson), anfragen)
    bloecke = []
    for nr, t in enumerate(treffer, 1):
        t["nr"] = nr
        t["quelle"] = _quellname(lesson, t["material_id"], t.get("material_name") or "")
        stelle = fundstelle(t)
        bloecke.append(f"[{nr}] Quelle: {t['quelle']}{', ' + stelle if stelle else ''}\n{t['text']}")
    text = (f"\n\n{ABSCHNITT_KOPF} (für diese Anfrage aus der Vektordatenbank abgerufen, die passendsten zuerst):\n\n"
            + ("\n\n".join(bloecke) if bloecke else "(keine passenden Auszüge gefunden)"))
    info = {"schrittart": schrittart, "modus": "rag",
            "anfragen": [a.strip()[:200] for a in anfragen if a and a.strip()],
            "treffer": [{"nr": t["nr"], "id": t["id"], "material_id": t["material_id"], "quelle": t["quelle"],
                         "fundstelle": fundstelle(t), "aehnlichkeit": t["aehnlichkeit"], "zeichen": len(t["text"])}
                        for t in treffer],
            "zeichen": sum(len(t["text"]) for t in treffer), "sekunden": round(time.time() - t0, 3),
            "modell": vektoren.modell()}
    return text, info


def verwendung(info: dict, data: dict) -> list[dict]:
    """Liest das Feld «auszuege» der Antwort, merkt die gültigen Nummern und gibt die Treffer zurück."""
    roh = data.pop("auszuege", None)
    nummern = []
    for x in roh if isinstance(roh, list) else ([roh] if roh is not None else []):
        try:
            n = int(str(x).strip().strip("[]"))
        except ValueError:
            continue
        if 1 <= n <= len(info["treffer"]) and n not in nummern:
            nummern.append(n)
    info["verwendet"] = nummern
    if roh not in (None, []) and len(nummern) < len(roh if isinstance(roh, list) else [roh]):
        info["verwendet_verworfen"] = str(roh)[:100]     # erfundene Nummern (vgl. N-01)
    return [info["treffer"][n - 1] for n in nummern]


def fundstellen_text(treffer: list[dict]) -> list[str]:
    """«OR Haftpflicht, S. 3, Art. 41» je verwendetem Auszug, ohne Doppelte."""
    out = []
    for t in treffer:
        s = t["quelle"] + (f", {t['fundstelle']}" if t.get("fundstelle") else "")
        if s not in out:
            out.append(s)
    return out


# ---------------------------------------------------------------- Editor

def material_fuer_editor(ids: list[str], anfragen: list[str], zeichen: int) -> str | None:
    """Für «Material prüfen» und «Lernziele vorschlagen» bei sehr grossem Material:
    Auszüge zu den Lernzielen bzw. zum Titel statt eines abgeschnittenen Anfangs.
    None, wenn das nicht geht (dann bleibt es beim bisherigen Vorgehen)."""
    if not ids or not vektoren.aktiv() or not vektoren.erreichbar():
        return None
    for mid in ids:
        m = materialien.holen(mid)
        if not m or vektoren.index_stand(m) not in ("bereit", "ohne_text"):
            return None
    try:
        treffer = suchen(ids, anfragen, anzahl=max(k(), 2 * len(anfragen)), zeichen=zeichen)
    except Exception as e:
        log.warning("Auszüge für den Editor nicht verfügbar: %s", e)
        return None
    namen = {mid: (materialien.holen(mid) or {}).get("name", mid) for mid in ids}
    return "\n\n".join(f"### Quelle: {namen.get(t['material_id'], '')} ({fundstelle(t)})\n\n{t['text']}"
                       for t in treffer)
