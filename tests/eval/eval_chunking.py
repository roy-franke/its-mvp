"""T-29, Entscheid E6: Welcher Overlap ist beim Chunking optimal?

Das Skript zerlegt ein Korpus mit verschiedenen Chunkgrössen und Overlaps
(app.vektoren.zerlegen, also genau wie das ITS), bettet die Chunks ein und
stellt Suchanfragen zu zufällig gewählten Textstellen (1 bis 3 Sätze aus einem
Absatz). Gemessen wird:

- voll@k: Anteil der Anfragen, bei denen einer der k besten Chunks die ganze
  Textstelle enthält. Genau das verbessert ein Overlap: Ohne ihn liegt eine
  Stelle, die über eine Chunkgrenze reicht, in keinem Chunk vollständig.
- teil@k: mindestens die Hälfte der Sätze der Stelle in einem Treffer.
- MRR: mittlerer Kehrwert des Rangs des ersten vollständigen Treffers.
- Faktor: Anzahl Chunks im Verhältnis zu «ohne Overlap» (Speicher, Rechenzeit
  beim Indexieren).
- Kontext: Zeichen der k Treffer zusammen (Länge des Prompts bei RAG).

Die Anfrage besteht aus rund 60 Prozent der Inhaltswörter der Stelle in
zufälliger Reihenfolge (Ersatz für eine Frage in eigenen Worten).

Einbettung: «its» nimmt den konfigurierten Anbieter des ITS (auf a9-mega
Ollama mit qwen3-embedding:0.6b), «spacy» deutsche Wortvektoren
(de_core_news_md), «tfidf» eine lexikalische Gewichtung ohne Modell.

    python tests/eval/eval_chunking.py --embedder its --dateien OR.pdf
    python tests/eval/eval_chunking.py --embedder spacy --europarl pfad/europarl_raw/german

Der Bericht landet in tests/eval/berichte/chunking_<Datum>.md.
"""

import argparse
import math
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import materialien, vektoren  # noqa: E402

STOPP = set("""der die das den dem des ein eine einer eines einem einen und oder aber auch als an auf aus bei bis
durch für gegen in im ins mit nach ohne über um unter von vor zu zum zur ist sind war waren wird werden wurde
hat haben hatte sein seine ihr ihre es er sie wir ich du man nicht kein keine so wie wenn dass daß da dann
noch nur schon sehr mehr diese dieser dieses diesem diesen sich was wer wo hier dort ob doch ja nein""".split())


# ---------------------------------------------------------------- Korpus

def korpus_lektionen() -> list[tuple[str, list[dict]]]:
    import json
    out = []
    for p in sorted((ROOT / "app" / "lessons").glob("*.json")):
        text = json.loads(p.read_text(encoding="utf-8")).get("material", "")
        if len(text) > 1500:
            out.append((p.stem, [{"seite": None, "text": text}]))
    return out


def korpus_dateien(pfade: list[str]) -> list[tuple[str, list[dict]]]:
    out = []
    for p in pfade:
        ext = materialien.extrahieren(Path(p).name, Path(p).read_bytes())
        out.append((Path(p).name, ext["seiten"]))
    return out


def korpus_europarl(ordner: str, max_zeichen: int) -> list[tuple[str, list[dict]]]:
    """Europarl ist tokenisiert, ein Satz pro Zeile: zurück zu Fliesstext in Absätzen zu 3 bis 8 Sätzen."""
    rnd = random.Random(7)
    out, total = [], 0
    for f in sorted(Path(ordner).glob("*.de")):
        zeilen = [z.strip() for z in f.read_text(encoding="utf-8", errors="replace").splitlines()]
        zeilen = [re.sub(r"\s+([,.;:!?)])", r"\1", re.sub(r'(\()\s+', r"\1", z)).replace(' " ', ' "')
                  for z in zeilen if z and not z.startswith("<")]
        absaetze, i = [], 0
        while i < len(zeilen):
            n = rnd.randint(3, 8)
            absaetze.append(" ".join(zeilen[i:i + n]))
            i += n
        text = "\n\n".join(absaetze)
        out.append((f.name, [{"seite": None, "text": text}]))
        total += len(text)
        if total >= max_zeichen:
            break
    return out


# ---------------------------------------------------------------- Einbettung

def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Spacy:
    name = "spacy de_core_news_md"

    def __init__(self):
        import spacy
        self.nlp = spacy.load("de_core_news_md", exclude=["parser", "ner", "lemmatizer", "tagger", "morphologizer",
                                                           "attribute_ruler", "senter"])

    def __call__(self, texte, art="dokument"):
        out = []
        for t in texte:
            vs = [tok.vector for tok in self.nlp.make_doc(t) if tok.has_vector and tok.lower_ not in STOPP]
            if not vs:
                out.append([0.0] * 300)
                continue
            out.append(_norm([sum(x) / len(vs) for x in zip(*vs)]))
        return out


class TfIdf:
    name = "tfidf"

    def __init__(self):
        self.df: Counter = Counter()
        self.n = 0

    def anpassen(self, texte):
        self.df, self.n = Counter(), len(texte)
        for t in texte:
            self.df.update(set(self._woerter(t)))

    @staticmethod
    def _woerter(t):
        return [w[:7] for w in re.findall(r"[a-zäöüß0-9]+", t.lower()) if w not in STOPP and len(w) > 2]

    def __call__(self, texte, art="dokument"):
        out = []
        for t in texte:
            tf = Counter(self._woerter(t))
            v = {w: (1 + math.log(c)) * math.log((self.n + 1) / (self.df.get(w, 0) + 1)) for w, c in tf.items()}
            n = math.sqrt(sum(x * x for x in v.values())) or 1.0
            out.append({w: x / n for w, x in v.items()})
        return out


class Its:
    def __init__(self):
        self.name = f"ITS {vektoren.anbieter()} {vektoren.modell()}"

    def __call__(self, texte, art="dokument"):
        return vektoren.einbetten(texte, art=art)


def aehnlich(a, b) -> float:
    if isinstance(a, dict):
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(w, 0.0) for w, x in a.items())
    return sum(x * y for x, y in zip(a, b))


# ---------------------------------------------------------------- Experiment

def stellen(korpus, anzahl: int, rnd: random.Random) -> list[dict]:
    """Zufällige Textstellen aus 1 bis 3 aufeinanderfolgenden Sätzen eines Absatzes."""
    kandidaten = []
    for name, seiten in korpus:
        for s in seiten:
            for absatz in re.split(r"\n\s*\n", s["text"]):
                ss = vektoren.saetze(absatz.replace("\n", " "))
                for i in range(len(ss)):
                    for n in (1, 2, 3):
                        teil = ss[i:i + n]
                        if len(teil) == n and 60 <= len(" ".join(teil)) <= 700:
                            kandidaten.append({"saetze": teil, "quelle": name})
    rnd.shuffle(kandidaten)
    out = kandidaten[:anzahl]
    for st in out:
        woerter = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß0-9-]+", " ".join(st["saetze"])) if w.lower() not in STOPP]
        k = max(4, round(len(woerter) * 0.6))
        st["anfrage"] = " ".join(rnd.sample(woerter, min(k, len(woerter))))
    return out


def _flach(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def lauf(korpus, embedder, groesse, overlap, fragen, k) -> dict:
    chunks = []
    for name, seiten in korpus:
        chunks += [vektoren.chunk_dokument(ch) for ch in vektoren.zerlegen(seiten, groesse, overlap)]
    if isinstance(embedder, TfIdf):
        embedder.anpassen(chunks)
    t0 = time.time()
    cv = embedder(chunks)
    qv = embedder([f["anfrage"] for f in fragen], art="abfrage")
    flach = [_flach(ch) for ch in chunks]
    voll = teil = rr = kontext = 0.0
    dicht = None
    if cv and not isinstance(cv[0], dict):
        import numpy as np                       # dichte Vektoren: Matrixprodukt statt Schleife
        dicht = np.asarray(qv, dtype=float) @ np.asarray(cv, dtype=float).T
    for j, (f, q) in enumerate(zip(fragen, qv)):
        if dicht is not None:
            rang = list(dicht[j].argsort()[::-1][:k])
        else:
            rang = sorted(range(len(chunks)), key=lambda i: -aehnlich(q, cv[i]))[:k]
        ganz, saetze = _flach(" ".join(f["saetze"])), [_flach(s) for s in f["saetze"]]
        erster = next((r for r, i in enumerate(rang) if ganz in flach[i]), None)
        voll += erster is not None
        rr += 1 / (erster + 1) if erster is not None else 0
        teil += any(sum(s in flach[i] for s in saetze) * 2 >= len(saetze) for i in rang)
        kontext += sum(len(chunks[i]) for i in rang)
    n = len(fragen)
    return {"groesse": groesse, "overlap": overlap, "chunks": len(chunks), "voll": 100 * voll / n,
            "teil": 100 * teil / n, "mrr": rr / n, "kontext": kontext / n, "sekunden": time.time() - t0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embedder", default="its", choices=["its", "spacy", "tfidf"])
    ap.add_argument("--dateien", nargs="*", default=[])
    ap.add_argument("--europarl", default="")
    ap.add_argument("--max-zeichen", type=int, default=600_000)
    ap.add_argument("--ohne-lektionen", action="store_true")
    ap.add_argument("--groessen", default="800,1200,1600")
    ap.add_argument("--overlaps", default="0,0.1,0.15,0.2,0.25,0.33", help="Anteile der Chunkgrösse")
    ap.add_argument("--fragen", type=int, default=400)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    korpus = ([] if a.ohne_lektionen else korpus_lektionen()) + korpus_dateien(a.dateien)
    if a.europarl:
        korpus += korpus_europarl(a.europarl, a.max_zeichen)
    zeichen = sum(len(s["text"]) for _, seiten in korpus for s in seiten)
    rnd = random.Random(a.seed)
    fragen = stellen(korpus, a.fragen, rnd)
    embedder = {"its": Its, "spacy": Spacy, "tfidf": TfIdf}[a.embedder]()
    laenge = sorted(len(" ".join(f["saetze"])) for f in fragen)
    q = lambda p: laenge[min(len(laenge) - 1, int(p * len(laenge)))]
    print(f"Korpus: {len(korpus)} Dokumente, {zeichen:,} Zeichen; {len(fragen)} Anfragen; {embedder.name}")
    print(f"Länge der Textstellen: Median {q(.5)}, 75 % {q(.75)}, 90 % {q(.9)} Zeichen")
    zeilen, ergebnisse = [], []
    for g in [int(x) for x in a.groessen.split(",")]:
        basis = None
        for anteil in [float(x) for x in a.overlaps.split(",")]:
            o = round(g * anteil)
            r = lauf(korpus, embedder, g, o, fragen, a.k)
            basis = basis or r["chunks"]
            r["faktor"] = r["chunks"] / basis
            r["anteil"] = anteil
            ergebnisse.append(r)
            zeile = (f"| {g} | {o} ({round(anteil * 100)} %) | {r['chunks']} | {r['faktor']:.2f} | {r['voll']:.1f} | "
                     f"{r['teil']:.1f} | {r['mrr']:.3f} | {r['kontext']:.0f} |")
            zeilen.append(zeile)
            print(zeile, flush=True)
    # Empfehlung: kleinster Overlap, dessen voll@k höchstens 1 Prozentpunkt unter dem besten seiner Grösse liegt
    empf = []
    for g in sorted({r["groesse"] for r in ergebnisse}):
        rs = [r for r in ergebnisse if r["groesse"] == g]
        bestes = max(r["voll"] for r in rs)
        wahl = min((r for r in rs if r["voll"] >= bestes - 1.0), key=lambda r: r["overlap"])
        empf.append(f"- Chunkgrösse {g}: Overlap {wahl['overlap']} Zeichen ({round(wahl['anteil'] * 100)} %), "
                    f"voll@{a.k} {wahl['voll']:.1f} % (bestes {bestes:.1f} %, ohne Overlap "
                    f"{rs[0]['voll']:.1f} %), Faktor {wahl['faktor']:.2f}")
    print("\n".join(empf))
    bericht = ROOT / "tests" / "eval" / "berichte" / f"chunking_{time.strftime('%Y-%m-%d_%H%M')}_{a.embedder}.md"
    bericht.parent.mkdir(parents=True, exist_ok=True)
    bericht.write_text(
        f"# Chunking-Experiment ({time.strftime('%d.%m.%Y %H:%M')})\n\n"
        f"Einbettung: {embedder.name}. Korpus: {len(korpus)} Dokumente, {zeichen:,} Zeichen "
        f"({', '.join(n for n, _ in korpus[:8])}{' …' if len(korpus) > 8 else ''}). "
        f"{len(fragen)} Anfragen, k = {a.k}, Seed {a.seed}.\n\n"
        f"Länge der Textstellen: Median {q(.5)}, 75 % {q(.75)}, 90 % {q(.9)} Zeichen.\n\n"
        f"| Grösse | Overlap | Chunks | Faktor | voll@{a.k} % | teil@{a.k} % | MRR | Kontext Zeichen |\n"
        "|---|---|---|---|---|---|---|---|\n" + "\n".join(zeilen) + "\n\n## Empfehlung\n\n" + "\n".join(empf) + "\n",
        encoding="utf-8")
    print(f"Bericht: {bericht}")


if __name__ == "__main__":
    main()
