// T-31: Version und Commit im Fussbereich jeder Seite.
// Die Seite braucht dafür nur <script src="/static/version.js" defer></script>.
(function () {
  function fuss() {
    let f = document.getElementById("its-version");
    if (!f) {
      f = document.createElement("footer");
      f.id = "its-version";
      f.className = "its-version";
      document.body.appendChild(f);
    }
    return f;
  }
  const stil = document.createElement("style");
  stil.textContent = ".its-version{font:12px/1.4 -apple-system,'Segoe UI',Roboto,sans-serif;color:#64748b;" +
    "text-align:center;padding:14px 16px 18px;}.its-version code{font-family:ui-monospace,Menlo,Consolas,monospace;" +
    "background:rgba(100,116,139,.12);padding:1px 5px;border-radius:4px}";
  document.head.appendChild(stil);
  function zeigen(v) {
    const f = fuss();
    f.textContent = "";
    f.append("ITS-Tutor · Version ");
    const c = document.createElement("code");
    c.textContent = v.version;
    f.append(c);
    if (v.commit) {
      f.append(" · Commit ");
      const h = document.createElement("code");
      h.textContent = v.commit;
      f.append(h);
    }
    f.title = "Semantische Version und Short-Hash des Commits: " + v.anzeige;
    f.dataset.version = v.anzeige;
  }
  function laden() {
    fetch("/api/version").then(r => r.ok ? r.json() : null).then(v => { if (v) zeigen(v); }).catch(() => {});
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", laden);
  else laden();
})();
