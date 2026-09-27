"""Persistenz: SQLite.

Tabellen:
- sessions: eine Zeile pro Lernsequenz (Person × Lektion × Versuch), inkl.
            Profil als JSON, Besitzer (user_key) und Status
- events:   vollständiges Protokoll aller Interaktionen (Lernpfad rekonstruierbar)
- users:    Lernende mit optionaler PIN (Entscheid E7)
- config:   Schlüssel/Wert, z.B. das Signaturgeheimnis

Status einer Lernsequenz (T-05): aktiv, pausiert, abgeschlossen, abgebrochen,
archiviert. Jeder Wechsel wird als Event status_geaendert protokolliert.
"""

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path(os.getenv("ITS_DB_PATH") or Path(__file__).resolve().parent.parent / "its.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                lesson_id TEXT NOT NULL,
                phase TEXT NOT NULL DEFAULT 'assessment',
                profile TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        _migrate(c)


def _columns(c, table: str) -> set[str]:
    return {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}


def _add_column(c, table: str, name: str, ddl: str) -> bool:
    """Ergänzt eine Spalte, falls sie fehlt (Migration ohne Datenverlust)."""
    if name in _columns(c, table):
        return False
    c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    return True


def _migrate(c):
    """Schemaänderungen für bestehende Datenbanken. Idempotent."""
    # T-01: vorab erzeugter nächster Schritt, getrennt vom Profil gespeichert,
    # damit ein laufender Vorabruf keine gleichzeitige Profiländerung überschreibt.
    _add_column(c, "sessions", "vorabruf", "TEXT")
    # T-04: von Lehrpersonen gestartete Durchläufe (Entscheid E3)
    _add_column(c, "sessions", "testlauf", "INTEGER NOT NULL DEFAULT 0")
    # T-05: Lernsequenzen gehören einer Person und haben einen Status
    neu = _add_column(c, "sessions", "user_key", "TEXT")
    _add_column(c, "sessions", "status", "TEXT NOT NULL DEFAULT 'aktiv'")
    _add_column(c, "sessions", "status_at", "REAL")
    _add_column(c, "sessions", "archived_at", "REAL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pin_hash TEXT,
            created_at REAL NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_key, lesson_id)")
    if neu:
        _migrate_t05(c)


def normalize_user(name: str | None) -> str:
    """Gross-/Kleinschreibung und Leerzeichen am Rand spielen keine Rolle."""
    return (name or "").strip().casefold()


def _migrate_t05(c):
    """Bestehende Sessions bekommen den eingegebenen Namen als Benutzer.

    Abgeschlossene Sessions erhalten den Status «abgeschlossen». Hat eine
    Person dieselbe Lektion mehrmals offen, bleibt die zuletzt aktive offen und
    die älteren werden archiviert (Regel: höchstens eine offene Sequenz pro
    Person und Lektion). Es wird nichts gelöscht.
    """
    now = time.time()
    rows = c.execute("SELECT id, name, lesson_id, phase, updated_at FROM sessions "
                     "ORDER BY updated_at DESC").fetchall()
    offen: set[tuple[str, str]] = set()
    for r in rows:
        key = normalize_user(r["name"])
        status = "abgeschlossen" if r["phase"] == "finished" else "aktiv"
        archived = None
        if (key, r["lesson_id"]) in offen:
            status, archived = "archiviert", now
        offen.add((key, r["lesson_id"]))
        c.execute("UPDATE sessions SET user_key = ?, status = ?, status_at = ?, archived_at = ? "
                  "WHERE id = ?", (key, status, r["updated_at"], archived, r["id"]))
        if archived:
            c.execute("INSERT INTO events (session_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
                      (r["id"], "status_geaendert",
                       json.dumps({"von": "aktiv", "nach": "archiviert",
                                   "grund": "Migration: neuere Sequenz derselben Lektion vorhanden"},
                                  ensure_ascii=False), now))
        c.execute("INSERT OR IGNORE INTO users (key, name, pin_hash, created_at) VALUES (?, ?, NULL, ?)",
                  (key, r["name"].strip(), now))
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id)")


def create_session(name: str, lesson_id: str, profile: dict, testlauf: bool = False,
                   user_key: str | None = None) -> str:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (id, name, lesson_id, phase, profile, created_at, updated_at, "
            "testlauf, user_key, status, status_at) "
            "VALUES (?, ?, ?, 'assessment', ?, ?, ?, ?, ?, 'aktiv', ?)",
            (sid, name, lesson_id, json.dumps(profile, ensure_ascii=False), now, now,
             int(testlauf), user_key or normalize_user(name), now),
        )
    return sid


STATUS = ("aktiv", "pausiert", "abgeschlossen", "abgebrochen", "archiviert")


def set_status(sid: str, status: str, grund: str = "") -> str | None:
    """Setzt den Status und protokolliert den Wechsel. Gibt den alten Status zurück."""
    assert status in STATUS
    now = time.time()
    with _conn() as c:
        row = c.execute("SELECT status FROM sessions WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return None
        alt = row["status"]
        if alt == status:
            return alt
        c.execute("UPDATE sessions SET status = ?, status_at = ?, updated_at = ?"
                  + (", archived_at = ?" if status == "archiviert" else "") + " WHERE id = ?",
                  (status, now, now, now, sid) if status == "archiviert" else (status, now, now, sid))
        payload = {"von": alt, "nach": status}
        if grund:
            payload["grund"] = grund
        c.execute("INSERT INTO events (session_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
                  (sid, "status_geaendert", json.dumps(payload, ensure_ascii=False), now))
    return alt


def sessions_of_user(user_key: str, include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM sessions WHERE user_key = ?"
    if not include_archived:
        sql += " AND status != 'archiviert'"
    with _conn() as c:
        rows = c.execute(sql + " ORDER BY updated_at DESC", (user_key,)).fetchall()
    return [_row(r) for r in rows]


def open_session_for(user_key: str, lesson_id: str) -> dict | None:
    """Die nicht archivierte Sequenz einer Person zu einer Lektion, falls vorhanden."""
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE user_key = ? AND lesson_id = ? "
                        "AND status != 'archiviert' ORDER BY updated_at DESC LIMIT 1",
                        (user_key, lesson_id)).fetchone()
    return _row(row) if row else None


def count_sessions_by_lesson() -> dict[str, dict]:
    with _conn() as c:
        rows = c.execute("SELECT lesson_id, status, COUNT(*) AS n FROM sessions "
                         "GROUP BY lesson_id, status").fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["lesson_id"], {})[r["status"]] = r["n"]
    return out


def _row(r) -> dict:
    d = dict(r)
    d["profile"] = json.loads(d["profile"])
    d.pop("vorabruf", None)
    return d


# ---------------------------------------------------------------- Benutzer

def get_user(key: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else None


def ensure_user(key: str, name: str) -> dict:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO users (key, name, pin_hash, created_at) VALUES (?, ?, NULL, ?)",
                  (key, name.strip(), time.time()))
    return get_user(key)


def set_user_pin(key: str, pin_hash: str):
    with _conn() as c:
        c.execute("UPDATE users SET pin_hash = ? WHERE key = ?", (pin_hash, key))


def get_session(sid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None:
        return None
    return _row(row)


def update_session(sid: str, phase: str | None = None, profile: dict | None = None):
    sets, vals = ["updated_at = ?"], [time.time()]
    if phase is not None:
        sets.append("phase = ?")
        vals.append(phase)
    if profile is not None:
        sets.append("profile = ?")
        vals.append(json.dumps(profile, ensure_ascii=False))
    vals.append(sid)
    with _conn() as c:
        c.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", vals)


def log_event(sid: str, etype: str, payload: dict):
    with _conn() as c:
        c.execute(
            "INSERT INTO events (session_id, type, payload, created_at) VALUES (?, ?, ?, ?)",
            (sid, etype, json.dumps(payload, ensure_ascii=False), time.time()),
        )


def last_event_id(sid: str) -> int:
    """Kennzahl für den Gesprächsstand: die ID des letzten Events der Session.

    Jede Verständnisfrage und jede Antwort erzeugt ein Event. Hat sich die Zahl
    seit einem Vorabruf geändert, passt der vorab erzeugte Schritt nicht mehr.
    """
    with _conn() as c:
        row = c.execute("SELECT MAX(id) AS m FROM events WHERE session_id = ?",
                        (sid,)).fetchone()
    return row["m"] or 0


def set_vorabruf(sid: str, data: dict | None):
    with _conn() as c:
        c.execute("UPDATE sessions SET vorabruf = ? WHERE id = ?",
                  (json.dumps(data, ensure_ascii=False) if data else None, sid))


def get_vorabruf(sid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT vorabruf FROM sessions WHERE id = ?", (sid,)).fetchone()
    return json.loads(row["vorabruf"]) if row and row["vorabruf"] else None


def get_events(sid: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY id", (sid,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def list_sessions() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
    return [_row(r) for r in rows]


def get_config(key: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_config(key: str, value: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
