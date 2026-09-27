"""Persistenz: SQLite.

Zwei Tabellen:
- sessions: eine Zeile pro Lerndurchlauf (Attempt), inkl. Profil als JSON
- events:   vollständiges Protokoll aller Interaktionen (Lernpfad rekonstruierbar)
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
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id)")


def create_session(name: str, lesson_id: str, profile: dict) -> str:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO sessions (id, name, lesson_id, phase, profile, created_at, updated_at) "
            "VALUES (?, ?, ?, 'assessment', ?, ?, ?)",
            (sid, name, lesson_id, json.dumps(profile, ensure_ascii=False), now, now),
        )
    return sid


def get_session(sid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["profile"] = json.loads(d["profile"])
    d.pop("vorabruf", None)
    return d


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
    out = []
    for r in rows:
        d = dict(r)
        d["profile"] = json.loads(d["profile"])
        d.pop("vorabruf", None)
        out.append(d)
    return out


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
