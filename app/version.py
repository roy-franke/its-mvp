"""T-31: Version des Tutors.

Die semantische Version (Major.Minor.Patch) steht in der Datei VERSION im
Projektordner. Dazu kommt der Short-Hash des Git-Commits, aus dem der Server
läuft. Er wird direkt aus dem Ordner .git gelesen, damit kein Git-Befehl
nötig ist (auf Windows ist git nicht immer im Pfad des Servers). Im
Docker-Container gibt es kein .git; dort setzt der Build `ITS_GIT_COMMIT`.

Anzeige nach SemVer 2.0 mit Build-Metadaten: «0.5.0+875a56b».

Regeln für das Hochzählen (Entscheid E7):
- Minor (0.5.0 -> 0.6.0) pro Auftrag mit neuen Funktionen,
- Patch (0.5.0 -> 0.5.1) für Korrekturen ohne neue Funktion,
- Major 1.0.0 für den Stand, der in den Pilotbetrieb geht.
Jede Version hat einen Eintrag in CHANGELOG.md.
"""

import os
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VERSION_DATEI = BASE / "VERSION"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_HASH = re.compile(r"^[0-9a-f]{7,40}$")

_cache: dict = {"zeit": 0.0, "info": None}
CACHE_SEKUNDEN = 30      # nach «git pull» ohne Neustart stimmt die Anzeige nach spätestens 30 s


def semver() -> str:
    try:
        text = VERSION_DATEI.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return text if SEMVER.match(text) else "0.0.0"


def _git_dir(basis: Path) -> Path | None:
    """Ordner .git, auch wenn .git eine Datei ist (Worktree: «gitdir: …»)."""
    g = basis / ".git"
    if g.is_dir():
        return g
    if g.is_file():
        try:
            inhalt = g.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if inhalt.startswith("gitdir:"):
            ziel = Path(inhalt.split(":", 1)[1].strip())
            return ziel if ziel.is_absolute() else (basis / ziel).resolve()
    return None


def _commondir(git: Path) -> Path:
    """Bei Worktrees liegen die Refs im gemeinsamen Ordner."""
    datei = git / "commondir"
    if datei.is_file():
        try:
            return (git / datei.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            pass
    return git


def git_commit(basis: Path = BASE) -> str | None:
    """Voller Hash des ausgecheckten Commits, oder None."""
    git = _git_dir(basis)
    if not git:
        return None
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if _HASH.match(head):
        return head                       # losgelöster HEAD
    if not head.startswith("ref:"):
        return None
    ref = head.split(":", 1)[1].strip()
    for ordner in (git, _commondir(git)):
        datei = ordner / ref
        if datei.is_file():
            wert = datei.read_text(encoding="utf-8").strip()
            if _HASH.match(wert):
                return wert
        packed = ordner / "packed-refs"
        if packed.is_file():
            for zeile in packed.read_text(encoding="utf-8").splitlines():
                teile = zeile.strip().split(" ")
                if len(teile) == 2 and teile[1] == ref and _HASH.match(teile[0]):
                    return teile[0]
    return None


def commit() -> tuple[str | None, str]:
    """(Short-Hash, Herkunft). Herkunft: env, git oder unbekannt."""
    env = (os.getenv("ITS_GIT_COMMIT") or "").strip().lower()
    if _HASH.match(env):
        return env[:7], "env"
    voll = git_commit()
    if voll:
        return voll[:7], "git"
    return None, "unbekannt"


def info() -> dict:
    jetzt = time.time()
    if _cache["info"] and jetzt - _cache["zeit"] < CACHE_SEKUNDEN:
        return dict(_cache["info"])
    v = semver()
    kurz, herkunft = commit()
    daten = {
        "version": v,
        "commit": kurz,
        "commit_herkunft": herkunft,
        "anzeige": f"{v}+{kurz}" if kurz else v,
    }
    _cache.update(zeit=jetzt, info=daten)
    return dict(daten)


def cache_leeren() -> None:
    _cache.update(zeit=0.0, info=None)
