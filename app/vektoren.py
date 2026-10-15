"""T-29: Lernmaterialien als Embeddings in einer Vektordatenbank (RAG, Teil 1).

Pipeline pro Lernmaterial (nach dem Upload im Hintergrund):

1. Text: seitenweise aus der Ablage (app/materialien.py, Extraktion beim Upload).
2. Chunking (`zerlegen`): Absätze und Sätze werden zu Chunks bis
   ITS_CHUNK_GROESSE Zeichen gepackt, an Überschriften («# …», «Art. 41»,
   «§ 3», «2.1 Titel») beginnt nach Möglichkeit ein neuer Chunk. Jeder Chunk
   übernimmt vom vorangehenden die letzten Sätze bis ITS_CHUNK_OVERLAP Zeichen
   (Overlap, Entscheid E6, ermittelt mit tests/eval/eval_chunking.py). Jeder
   Chunk kennt Seite(n) und Abschnitt, damit Antworten eine Fundstelle nennen.
3. Embeddings (`einbetten`): beim gleichen Anbieter wie das Chat-Modell
   (Entscheid E4). Ollama: /api/embed mit qwen3-embedding:0.6b, OpenAI:
   /v1/embeddings mit text-embedding-3-small, Mock: deterministische
   Wortstamm-Vektoren für Tests und Demos ohne Modell.
4. Speichern in ChromaDB (Entscheid E1), einem eigenen Dienst
   (ITS_VEKTOR_DB_URL). Eine Sammlung pro Embedding-Modell, weil Vektoren
   verschiedener Modelle nicht vergleichbar sind. Jeder Eintrag trägt
   Material-ID, Name, Datei, Seite, Abschnitt, Modell und Chunk-Parameter.
   Der Katalog (materialien.index_info) hält Modell, Parameter, Anzahl
   Chunks, Zeitpunkt und Dauer.

Suche (`suchen`, für T-30): Abfrage einbetten (bei Qwen3 mit der empfohlenen
Instruktion), nächste Nachbarn nur innerhalb der Materialien der Lektion.
"""

import hashlib
import logging
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx

from . import materialien

log = logging.getLogger("its.vektoren")

STANDARD_MODELLE = {"ollama": "qwen3-embedding:0.6b", "openai": "text-embedding-3-small", "mock": "mock-wortstamm-256"}
# Qwen3-Embedding erwartet bei Abfragen eine Instruktion, Dokumente bleiben ohne.
QWEN3_PRAEFIX = ("Instruct: Given a learner's question or a tutoring task, retrieve passages of the "
                 "teaching material that answer it\nQuery: ")
MOCK_DIMENSION = 256
STAPEL = 32


class VektorFehler(Exception):
    pass


# ---------------------------------------------------------------- Konfiguration

def url() -> str:
    return (os.getenv("ITS_VEKTOR_DB_URL") or "").strip().rstrip("/")


def aktiv() -> bool:
    return bool(url()) and anbieter() is not None


def anbieter() -> str | None:
    """Embedding-Anbieter: ITS_EMBED_PROVIDER oder passend zum Chat-Anbieter."""
    wahl = (os.getenv("ITS_EMBED_PROVIDER") or "auto").strip().lower()
    if wahl in ("aus", "off", "none", "false"):
        return None
    if wahl == "auto":
        llm = (os.getenv("LLM_PROVIDER") or "mock").strip().lower()
        return llm if llm in STANDARD_MODELLE else None      # anthropic hat keine Embeddings
    return wahl if wahl in STANDARD_MODELLE else None


def modell() -> str:
    a = anbieter() or "mock"
    return (os.getenv("ITS_EMBED_MODEL") or "").strip() or STANDARD_MODELLE[a]


def abfrage_praefix() -> str:
    roh = os.getenv("ITS_EMBED_QUERY_PREFIX")
    if roh is not None:
        return roh.replace("\\n", "\n")
    return QWEN3_PRAEFIX if "qwen3-embedding" in modell().lower() else ""


def chunk_groesse() -> int:
    return max(200, int(os.getenv("ITS_CHUNK_GROESSE", "1200")))


def chunk_overlap() -> int:
    return max(0, min(int(os.getenv("ITS_CHUNK_OVERLAP", "300")), chunk_groesse() // 2))


def sammlung_name(a: str | None = None, m: str | None = None) -> str:
    """Chroma-Sammlung pro Modell, z.B. «its-ollama-qwen3-embedding-0.6b»."""
    roh = f"its-{a or anbieter() or 'mock'}-{m or modell()}".lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", roh).strip("-._")[:200]
    return name if len(name) >= 3 else "its-vektoren"


def parameter() -> dict:
    """Modell und Parameter, wie sie zu jedem Material gespeichert werden (AK a)."""
    return {"anbieter": anbieter(), "modell": modell(), "chunk_groesse": chunk_groesse(),
            "overlap": chunk_overlap(), "distanz": "cosine", "abfrage_praefix": abfrage_praefix(),
            "sammlung": sammlung_name()}


# ---------------------------------------------------------------- Chunking

_STARK = re.compile(r"^(#{1,6}\s+\S|Art\.?\s*\d+[a-z]?\b|§\s*\d+|(\d+\.){1,3}\d*\s+[A-ZÄÖÜ])")
_SATZENDE = re.compile(r"(?<=[.!?…])\s+(?=[\"«„(]?[A-ZÄÖÜ0-9])")


def ist_ueberschrift(zeile: str, laengste: int = 0) -> bool:
    """Überschrift? Stark: «# …», «Art. 41 …», «§ 3 …», «2.1 Titel». Schwach: kurze
    Zeile ohne Satzzeichen am Ende, deutlich kürzer als die übrigen Zeilen des
    Absatzes (im PDF umbrochene Sätze sind etwa gleich lang) oder allein stehend."""
    a = zeile.strip()
    if len(a) < 2 or len(a) > 100:
        return False
    if _STARK.match(a):
        return len(a.split()) <= 14 and not a.endswith((",", ";"))
    if a.endswith((".", ",", ";", ":")) or "," in a or not a[0].isupper() or len(a.split()) > 8:
        return False
    return laengste == 0 or len(a) < 0.6 * laengste


_ABKUERZUNGEN = {"art", "abs", "ziff", "lit", "bzw", "usw", "nr", "s", "vgl", "ca", "dr", "prof", "bspw",
                 "zb", "dh", "ua", "evtl", "inkl", "ggf", "sog", "bzgl", "etc", "st", "chr", "jh", "mio", "mrd",
                 "fr", "or", "zgb", "stgb", "svg", "al", "ff", "f", "kap", "bd", "aufl", "hrsg", "sr"}


def saetze(text: str) -> list[str]:
    """Teilt an Satzenden, nicht nach Abkürzungen («Art. 41», «z.B. der») oder Ordnungszahlen."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    out, start = [], 0
    for m in _SATZENDE.finditer(text):
        vorher = text[start:m.start()]
        wort = re.findall(r"([A-Za-zÄÖÜäöü.]+|\d+)[.!?…]$", vorher)
        w = (wort[0] if wort else "").replace(".", "").lower()
        if vorher.endswith(".") and (w in _ABKUERZUNGEN or w.isdigit()
                                     or (len(w) == 1 and w.isalpha())):
            continue
        out.append(vorher.strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


def _hart_teilen(text: str, groesse: int) -> list[str]:
    """Ein Satz, der länger als ein Chunk ist, wird an Wortgrenzen geteilt."""
    out, aktuell = [], ""
    for wort in text.split(" "):
        if aktuell and len(aktuell) + 1 + len(wort) > groesse:
            out.append(aktuell)
            aktuell = wort
        else:
            aktuell = f"{aktuell} {wort}".strip()
    if aktuell:
        out.append(aktuell)
    return out


def zerlegen(seiten: list[dict], groesse: int | None = None, overlap: int | None = None) -> list[dict]:
    """Zerlegt seitenweisen Text in Chunks mit Overlap.

    Rückgabe: [{"text", "seite_von", "seite_bis", "abschnitt", "nr"}]. Der
    Overlap besteht aus ganzen Sätzen vom Ende des vorangehenden Chunks
    (höchstens `overlap` Zeichen; ist schon der letzte Satz länger, dessen
    letzte Wörter). Er gilt innerhalb eines Abschnitts: Beginnt mit einer
    Überschrift ein neuer Abschnitt, startet der Chunk mit ihr, ohne Text
    aus dem vorangehenden Abschnitt (etwa aus einem anderen Gesetzesartikel).
    """
    groesse = groesse or chunk_groesse()
    overlap = chunk_overlap() if overlap is None else max(0, min(overlap, groesse // 2))
    # 1. Einheiten: Sätze mit Seite und aktuellem Abschnitt
    einheiten: list[dict] = []
    abschnitt = ""
    for s in seiten:
        for absatz in re.split(r"\n\s*\n", s.get("text") or ""):
            zeilen = [z.strip() for z in absatz.split("\n") if z.strip()]
            if not zeilen:
                continue
            laengste = max(len(z) for z in zeilen) if len(zeilen) > 1 else 0
            puffer: list[str] = []

            def fliesstext():
                for satz in saetze(" ".join(puffer)):
                    for teil in (_hart_teilen(satz, groesse) if len(satz) > groesse else [satz]):
                        einheiten.append({"text": teil, "seite": s.get("seite"), "abschnitt": abschnitt,
                                          "kopf": False})
                if puffer and einheiten:
                    einheiten[-1]["absatzende"] = True
                puffer.clear()

            for z in zeilen:
                if ist_ueberschrift(z, laengste):
                    fliesstext()
                    abschnitt = z.lstrip("# ").strip()
                    einheiten.append({"text": z, "seite": s.get("seite"), "abschnitt": abschnitt, "kopf": True})
                else:
                    puffer.append(z)
            fliesstext()
    # 2. Packen
    chunks: list[dict] = []
    aktuell: list[dict] = []

    def laenge(liste):
        return sum(len(e["text"]) + 1 for e in liste)

    def abschliessen():
        if not aktuell or all(e.get("_overlap") for e in aktuell):
            return
        teile, vorher = [], None
        for e in aktuell:
            if vorher is not None:
                teile.append("\n\n" if (vorher.get("absatzende") or vorher.get("kopf") or e.get("kopf")) else " ")
            teile.append(e["text"])
            vorher = e
        seiten_nr = [e["seite"] for e in aktuell if e["seite"] is not None]
        eigene = [e for e in aktuell if not e.get("_overlap")]
        # Abschnitt: alle Überschriften, die der Chunk berührt («Art. 41; Art. 42»)
        abschnitte = list(dict.fromkeys(e["abschnitt"] for e in (eigene or aktuell) if e["abschnitt"]))
        chunks.append({"text": "".join(teile).strip(), "seite_von": min(seiten_nr) if seiten_nr else None,
                       "seite_bis": max(seiten_nr) if seiten_nr else None,
                       "abschnitt": "; ".join(abschnitte)[:200], "nr": len(chunks)})

    def overlap_von(liste):
        if overlap <= 0:
            return []
        out, summe = [], 0
        for e in reversed([x for x in liste if not x.get("kopf")]):
            if summe + len(e["text"]) > overlap:
                if not out:     # schon der letzte Satz ist zu lang: seine letzten Wörter
                    woerter, rest = [], ""
                    for w in reversed(e["text"].split(" ")):
                        if len(rest) + len(w) + 1 > overlap:
                            break
                        woerter.insert(0, w)
                        rest = " ".join(woerter)
                    if rest:
                        out.insert(0, dict(e, text="… " + rest, _overlap=True, absatzende=False))
                break
            out.insert(0, dict(e, _overlap=True))
            summe += len(e["text"]) + 1
        return out

    for e in einheiten:
        neuer_abschnitt = e.get("kopf") and laenge(aktuell) >= groesse // 2
        if aktuell and (laenge(aktuell) + len(e["text"]) > groesse or neuer_abschnitt):
            eigene = [x for x in aktuell if not x.get("_overlap")]
            if eigene and all(x.get("kopf") for x in eigene) and not e.get("kopf"):
                aktuell = eigene          # nur Überschriften: sie gehören zum folgenden Text
            else:
                abschliessen()
                # Overlap innerhalb eines Abschnitts; eine neue Überschrift beginnt sauber
                aktuell = [] if e.get("kopf") else overlap_von(aktuell)
                # Overlap darf zusammen mit der nächsten Einheit die Grösse nicht sprengen
                while aktuell and laenge(aktuell) + len(e["text"]) > groesse:
                    aktuell.pop(0)
        aktuell.append(e)
    abschliessen()
    return chunks


def chunk_dokument(chunk: dict) -> str:
    """Text, der eingebettet und später als Auszug gezeigt wird: mit Abschnitt als Kontext."""
    kopf = chunk.get("abschnitt") or ""
    if kopf and not chunk["text"].lstrip("# ").startswith(kopf):
        return f"[{kopf}] {chunk['text']}"
    return chunk["text"]


# ---------------------------------------------------------------- Embeddings

def _mock_vektor(text: str) -> list[float]:
    """Wortstämme (erste 6 Buchstaben) per Hash in 256 Dimensionen, normiert."""
    v = [0.0] * MOCK_DIMENSION
    for wort in re.findall(r"[a-zäöüß0-9]+", text.lower()):
        if len(wort) < 3:
            continue
        h = int(hashlib.md5(wort[:6].encode()).hexdigest(), 16)
        v[h % MOCK_DIMENSION] += 1.0 if (h >> 8) % 2 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def einbetten(texte: list[str], art: str = "dokument") -> list[list[float]]:
    """Embeddings für Texte; art «abfrage» setzt das Abfragepräfix davor."""
    a = anbieter()
    if a is None:
        raise VektorFehler("Kein Embedding-Anbieter (ITS_EMBED_PROVIDER, bei Anthropic z.B. ollama setzen)")
    if art == "abfrage":
        texte = [abfrage_praefix() + t for t in texte]
    out: list[list[float]] = []
    for i in range(0, len(texte), STAPEL):
        teil = texte[i:i + STAPEL]
        if a == "mock":
            out += [_mock_vektor(t) for t in teil]
        elif a == "ollama":
            base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            r = httpx.post(f"{base}/api/embed", json={"model": modell(), "input": teil, "truncate": True,
                                                      "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m")},
                           timeout=float(os.getenv("LLM_TIMEOUT", "300")))
            if r.status_code == 404:
                raise VektorFehler(f"Embedding-Modell {modell()} fehlt in Ollama: ollama pull {modell()}")
            r.raise_for_status()
            out += r.json()["embeddings"]
        elif a == "openai":
            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            r = httpx.post(f"{base}/embeddings", headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"},
                           json={"model": modell(), "input": teil}, timeout=float(os.getenv("LLM_TIMEOUT", "300")))
            r.raise_for_status()
            out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    return out


# ---------------------------------------------------------------- ChromaDB

_client_lock = threading.Lock()
_client: dict = {"url": None, "client": None}
_erreichbar: dict = {"zeit": 0.0, "wert": False, "fehler": ""}


def _chroma():
    with _client_lock:
        if _client["url"] != url() or _client["client"] is None:
            import chromadb
            from chromadb.config import Settings
            u = urlparse(url() if "://" in url() else f"http://{url()}")
            _client["client"] = chromadb.HttpClient(
                host=u.hostname or "localhost", port=u.port or (443 if u.scheme == "https" else 8000),
                ssl=u.scheme == "https", settings=Settings(anonymized_telemetry=False))
            _client["url"] = url()
        return _client["client"]


def _sammlung(name: str | None = None):
    return _chroma().get_or_create_collection(name or sammlung_name(), configuration={"hnsw": {"space": "cosine"}},
                                              embedding_function=None)


def erreichbar(neu: bool = False) -> bool:
    """Heartbeat der Vektordatenbank, 30 Sekunden zwischengespeichert."""
    if not url():
        return False
    if not neu and time.time() - _erreichbar["zeit"] < 30:
        return _erreichbar["wert"]
    try:
        _chroma().heartbeat()
        _erreichbar.update(zeit=time.time(), wert=True, fehler="")
    except Exception as e:                   # Verbindung, Version, Import
        _erreichbar.update(zeit=time.time(), wert=False, fehler=f"{type(e).__name__}: {e}"[:300])
        log.warning("Vektordatenbank %s nicht erreichbar: %s", url(), _erreichbar["fehler"])
    return _erreichbar["wert"]


def status() -> dict:
    return {"aktiv": aktiv(), "url": url(), "anbieter": anbieter(), "modell": modell(),
            "sammlung": sammlung_name(), "erreichbar": erreichbar() if aktiv() else False,
            "fehler": _erreichbar["fehler"], "chunk_groesse": chunk_groesse(), "overlap": chunk_overlap()}


def index_stand(m: dict) -> str:
    """Stand für die Oberfläche: «veraltet», wenn mit einem anderen Modell indexiert."""
    st = m.get("index_status") or "offen"
    info = m.get("index_info") or {}
    if st == "bereit" and aktiv() and info.get("sammlung") != sammlung_name():
        return "veraltet"
    if st in ("offen", "aus") and not aktiv() and m.get("zeichen"):
        return "aus"
    return st


# ---------------------------------------------------------------- Indexieren

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="its-index")
_laufend: set[str] = set()


def indexieren(mid: str) -> dict:
    """Material zerlegen, einbetten und in Chroma ablegen (ersetzt einen alten Index)."""
    m = materialien.holen(mid)
    if not m:
        raise VektorFehler(f"Material {mid} gibt es nicht")
    if not aktiv():
        materialien.setzen(mid, index_status="aus")
        return materialien.holen(mid)
    seiten = materialien.seiten(mid)
    if not any((s.get("text") or "").strip() for s in seiten):
        materialien.setzen(mid, index_status="ohne_text")
        return materialien.holen(mid)
    params = parameter()
    materialien.setzen(mid, index_status="laeuft", index_info=dict(params, gestartet_am=time.time()))
    t0 = time.time()
    try:
        chunks = zerlegen(seiten)
        dokumente = [chunk_dokument(c) for c in chunks]
        vektoren = einbetten(dokumente)
        sammlung = _sammlung()
        sammlung.delete(where={"material_id": mid})
        metadaten = []
        for c in chunks:
            md = {"material_id": mid, "material_name": m["name"], "dateiname": m["dateiname"], "chunk": c["nr"],
                  "abschnitt": c["abschnitt"][:200], "zeichen": len(c["text"]), "embed_anbieter": params["anbieter"],
                  "embed_modell": params["modell"], "chunk_groesse": params["chunk_groesse"],
                  "overlap": params["overlap"], "speicherort": m["speicherort"]}
            if c["seite_von"] is not None:
                md.update(seite_von=c["seite_von"], seite_bis=c["seite_bis"])
            metadaten.append(md)
        for i in range(0, len(chunks), 256):
            sammlung.add(ids=[f"{mid}:{c['nr']}" for c in chunks[i:i + 256]], embeddings=vektoren[i:i + 256],
                         documents=dokumente[i:i + 256], metadatas=metadaten[i:i + 256])
        info = dict(params, dimension=len(vektoren[0]) if vektoren else 0, anzahl_chunks=len(chunks),
                    indexiert_am=time.time(), dauer_sekunden=round(time.time() - t0, 2),
                    zeichen_mittel=round(sum(len(c["text"]) for c in chunks) / max(len(chunks), 1)))
        materialien.setzen(mid, index_status="bereit", index_info=info)
        log.info("Material %s indexiert: %d Chunks, %s, %.1fs", mid, len(chunks), params["modell"], info["dauer_sekunden"])
    except Exception as e:
        fehler = f"{type(e).__name__}: {e}"[:400]
        materialien.setzen(mid, index_status="fehler", index_info=dict(params, fehler=fehler, fehler_am=time.time()))
        log.warning("Indexierung von %s gescheitert: %s", mid, fehler)
    return materialien.holen(mid)


def im_hintergrund(mid: str) -> None:
    """Indexierung in einem eigenen Thread (eine nach der anderen)."""
    if not aktiv():
        m = materialien.holen(mid)
        if m and m["index_status"] == "offen":
            materialien.setzen(mid, index_status="aus")
        return
    if mid in _laufend:
        return
    _laufend.add(mid)
    materialien.setzen(mid, index_status="laeuft")

    def lauf():
        try:
            indexieren(mid)
        finally:
            _laufend.discard(mid)
    _executor.submit(lauf)


def warten(timeout: float = 30) -> None:
    """Für Tests: wartet, bis alle angestossenen Indexierungen fertig sind."""
    ende = time.time() + timeout
    while _laufend and time.time() < ende:
        time.sleep(0.05)


def nachholen() -> int:
    """Beim Start: unterbrochene oder offene Indexierungen nachholen."""
    if not aktiv():
        return 0
    n = 0
    for m in materialien.alle(include_archived=True):
        if m["index_status"] in ("offen", "laeuft", "aus") and m["zeichen"]:
            im_hintergrund(m["id"])
            n += 1
    return n


# ---------------------------------------------------------------- Suche (T-30)

def suchen(anfrage: str, material_ids: list[str], k: int = 6) -> list[dict]:
    """Die k ähnlichsten Chunks aus den genannten Materialien."""
    if not material_ids or not anfrage.strip():
        return []
    vektor = einbetten([anfrage], art="abfrage")[0]
    where = {"material_id": material_ids[0]} if len(material_ids) == 1 else {"material_id": {"$in": material_ids}}
    r = _sammlung().query(query_embeddings=[vektor], n_results=k, where=where,
                          include=["documents", "metadatas", "distances"])
    treffer = []
    for i, doc, md, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]):
        treffer.append({"id": i, "text": doc, "material_id": md.get("material_id"),
                        "material_name": md.get("material_name"), "dateiname": md.get("dateiname"),
                        "seite_von": md.get("seite_von"), "seite_bis": md.get("seite_bis"),
                        "abschnitt": md.get("abschnitt", ""), "chunk": md.get("chunk"),
                        "abstand": round(float(dist), 4), "aehnlichkeit": round(1 - float(dist), 4)})
    return treffer


def material_entfernen(mid: str) -> None:
    """Embeddings eines Materials entfernen (wird beim Archivieren bewusst NICHT aufgerufen)."""
    _sammlung().delete(where={"material_id": mid})
