"""T-31 Versionierung und T-27 Favicon."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import version
from app.main import app

BASE = Path(__file__).resolve().parent.parent
SEITEN = ["index.html", "teacher.html", "lessons.html", "lesson_editor.html", "teacher_login.html",
          ]


def test_version_ist_semver_und_steht_im_changelog():
    v = (BASE / "VERSION").read_text(encoding="utf-8").strip()
    assert version.SEMVER.match(v)
    assert f"## {v} " in (BASE / "CHANGELOG.md").read_text(encoding="utf-8")


def test_api_version_mit_commit_aus_git(tmp_path, monkeypatch):
    monkeypatch.delenv("ITS_GIT_COMMIT", raising=False)
    version.cache_leeren()
    d = TestClient(app).get("/api/version").json()
    assert d["version"] == version.semver()
    if (BASE / ".git").exists():
        assert re.fullmatch(r"[0-9a-f]{7}", d["commit"]) and d["commit_herkunft"] == "git"
        assert d["anzeige"] == f"{d['version']}+{d['commit']}"
    version.cache_leeren()


def test_commit_aus_umgebung_hat_vorrang(monkeypatch):
    monkeypatch.setenv("ITS_GIT_COMMIT", "ABCDEF1234567")
    version.cache_leeren()
    d = version.info()
    assert d["commit"] == "abcdef1" and d["commit_herkunft"] == "env" and d["anzeige"].endswith("+abcdef1")
    version.cache_leeren()


def test_git_lesen_ohne_git_befehl(tmp_path):
    """HEAD mit Ref, gepackte Refs, losgelöster HEAD und Worktree-Datei."""
    git = tmp_path / "repo" / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "refs" / "heads" / "main").write_text("1234567890abcdef1234567890abcdef12345678\n")
    assert version.git_commit(tmp_path / "repo").startswith("1234567")
    (git / "refs" / "heads" / "main").unlink()
    (git / "packed-refs").write_text("# pack-refs with: peeled\n"
                                     "fedcba9876543210fedcba9876543210fedcba98 refs/heads/main\n")
    assert version.git_commit(tmp_path / "repo").startswith("fedcba9")
    (git / "HEAD").write_text("0123456789012345678901234567890123456789\n")
    assert version.git_commit(tmp_path / "repo") == "0123456789012345678901234567890123456789"
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {git}\n")
    assert version.git_commit(wt).startswith("0123456")
    assert version.git_commit(tmp_path / "leer") is None


def test_ohne_git_und_ohne_umgebung(monkeypatch, tmp_path):
    monkeypatch.delenv("ITS_GIT_COMMIT", raising=False)
    monkeypatch.setattr(version, "BASE", tmp_path)
    monkeypatch.setattr(version, "git_commit", lambda basis=tmp_path: None)
    version.cache_leeren()
    d = version.info()
    assert d["commit"] is None and d["anzeige"] == d["version"]
    version.cache_leeren()


def test_info_nennt_version():
    assert TestClient(app).get("/api/info").json()["version"] == version.info()["anzeige"]


def test_jede_seite_hat_favicon_und_versionsfuss():
    for name in SEITEN:
        html = (BASE / "static" / name).read_text(encoding="utf-8")
        assert 'href="/static/favicon.svg"' in html, name
        assert 'href="/favicon.ico"' in html, name
        assert '<script src="/static/version.js" defer></script>' in html, name


def test_favicon_ohne_anmeldung(monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "geheim")
    c = TestClient(app)
    r = c.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon" and r.content[:4] == b"\x00\x00\x01\x00"
    r = c.get("/static/favicon.svg")
    assert r.status_code == 200 and "<svg" in r.text
    assert c.get("/static/apple-touch-icon.png").status_code == 200
    assert c.get("/api/version").status_code == 200
