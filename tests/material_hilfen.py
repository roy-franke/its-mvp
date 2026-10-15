"""Testdateien für die Lernmaterialien (L-01, T-29, T-30) ohne zusätzliche Pakete."""

import io
import struct
import zlib

from fastapi.testclient import TestClient


def pdf(seiten: list[str], moddate: str = "D:20260912143000") -> bytes:
    """Minimales, gültiges PDF mit einer Textzeile pro Absatz und Seite."""
    objekte: list[bytes] = []

    def obj(inhalt: bytes) -> int:
        objekte.append(inhalt)
        return len(objekte)

    katalog = obj(b"")                    # Platzhalter, wird unten gesetzt
    seitenbaum = obj(b"")
    schrift = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kinder = []
    for text in seiten:
        zeilen = []
        for z in text.split("\n"):
            z = z.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            zeilen.append(f"({z}) Tj 0 -16 Td")
        strom = ("BT /F1 11 Tf 40 800 Td " + " ".join(zeilen) + " ET").encode("cp1252")
        inhalt = obj(b"<< /Length %d >>\nstream\n" % len(strom) + strom + b"\nendstream")
        kinder.append(obj(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
                          b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (seitenbaum, inhalt, schrift)))
    objekte[katalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % seitenbaum
    objekte[seitenbaum - 1] = (b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kinder)
                               + b"] /Count %d >>" % len(kinder))
    info = obj(b"<< /Title (Test) /ModDate (" + moddate.encode() + b") >>")
    aus = io.BytesIO()
    aus.write(b"%PDF-1.4\n")
    positionen = []
    for i, o in enumerate(objekte, 1):
        positionen.append(aus.tell())
        aus.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = aus.tell()
    aus.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1))
    for p in positionen:
        aus.write(b"%010d 00000 n \n" % p)
    aus.write(b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
              % (len(objekte) + 1, katalog, info, xref))
    return aus.getvalue()


def docx(absaetze: list[tuple[str, str]]) -> bytes:
    """Word-Datei; absaetze = [(stil, text)], stil z.B. "Heading 1" oder "Normal"."""
    import datetime

    import docx as python_docx
    d = python_docx.Document()
    for stil, text in absaetze:
        d.add_paragraph(text, style=stil)
    d.core_properties.modified = datetime.datetime(2026, 9, 1, 8, 0, tzinfo=datetime.timezone.utc)
    aus = io.BytesIO()
    d.save(aus)
    return aus.getvalue()


def png(breite: int = 4, hoehe: int = 4) -> bytes:
    roh = b"".join(b"\x00" + b"\xff\xff\xff" * breite for _ in range(hoehe))

    def chunk(art: bytes, daten: bytes) -> bytes:
        return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", breite, hoehe, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(roh)) + chunk(b"IEND", b""))


HAFTUNG = [
    "Haftung aus unerlaubter Handlung\nWer einem andern widerrechtlich Schaden zufuegt, wird ihm zum Ersatze "
    "verpflichtet (Art. 41 OR).\nVoraussetzungen sind Schaden, Widerrechtlichkeit, Kausalzusammenhang "
    "und Verschulden.",
    "Tierhalterhaftung\nFuer den von einem Tier angerichteten Schaden haftet, wer dasselbe haelt (Art. 56 OR).\n"
    "Der Tierhalter kann sich entlasten, wenn er die gebotene Sorgfalt nachweist.",
    "Geschaeftsherrenhaftung\nDer Geschaeftsherr haftet fuer den Schaden, den seine Arbeitnehmer in "
    "Ausuebung ihrer Verrichtungen verursacht haben (Art. 55 OR).",
]


def hochladen(client: TestClient | None = None, dateiname: str = "haftung.pdf", daten: bytes | None = None,
              **meta) -> dict:
    c = client or TestClient(__import__("app.main", fromlist=["app"]).app)
    felder = {"name": meta.pop("name", ""), "beschreibung": meta.pop("beschreibung", ""),
              "niveau": meta.pop("niveau", ""), "hochgeladen_von": meta.pop("hochgeladen_von", "Test"),
              "faecher": __import__("json").dumps(meta.pop("faecher", [])),
              "tags": __import__("json").dumps(meta.pop("tags", []))}
    meta.setdefault("trotzdem", "true")        # gleiche Testdatei mehrfach erlaubt
    felder.update({k: str(v) for k, v in meta.items()})
    r = c.post("/api/teacher/materialien", files={"file": (dateiname, daten if daten is not None else pdf(HAFTUNG))},
               data=felder)
    return {**(r.json() if r.headers.get("content-type", "").startswith("application/json") else {}), "http": r.status_code}
