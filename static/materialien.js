// L-01/L-02/L-03: Gemeinsame Bausteine für die Lernmaterialien-Ablage.
// Verwendet auf der Seite «Lernmaterialien» und im Lektionseditor.
//
//   ITSMaterial.uploadDialog(files, { onFertig(materialien) })
//   ITSMaterial.tabelle(container, { modus: "verwalten" | "auswahl", gewaehlt: Set, onAuswahl(ids), onAenderung() })
//   ITSMaterial.detailDialog(id, { onAenderung() })
(function () {
  "use strict";

  const BESCHREIBUNG_MAX = 128;
  const stil = document.createElement("style");
  stil.textContent = `
  .itsm-modal { position:fixed; inset:0; background:rgba(15,23,42,.45); display:flex; align-items:flex-start;
                justify-content:center; padding:24px 16px; z-index:50; overflow:auto; }
  .itsm-box { background:#fff; border-radius:12px; padding:20px 22px; max-width:760px; width:100%;
              box-shadow:0 10px 40px rgba(15,23,42,.25); font-size:.92rem; }
  .itsm-box h2 { margin:0 0 4px; font-size:1.1rem; }
  .itsm-box .itsm-sub { color:#64748b; font-size:.85rem; margin:0 0 12px; }
  .itsm-feld { margin:12px 0 0; }
  .itsm-feld > label { display:block; font-weight:600; margin-bottom:5px; }
  .itsm-feld .itsm-hilfe { font-weight:400; color:#64748b; font-size:.8rem; }
  .itsm-box input[type=text], .itsm-box input[type=date], .itsm-filter input, .itsm-filter select {
      width:100%; padding:8px 10px; border:1px solid #e2e8f0; border-radius:8px; font:inherit; background:#fff; }
  .itsm-datei { border:1px solid #e2e8f0; border-radius:10px; padding:10px 12px; margin-top:10px; background:#fbfcfd; }
  .itsm-datei .itsm-dname { font-weight:600; font-size:.85rem; color:#334155; margin-bottom:6px; word-break:break-all; }
  .itsm-datei .itsm-zeile { display:grid; grid-template-columns: 1fr 1.6fr; gap:8px; }
  .itsm-zaehler { font-size:.75rem; color:#64748b; text-align:right; }
  .itsm-zaehler.zu-lang { color:#dc2626; font-weight:600; }
  .itsm-status { font-size:.8rem; margin-top:6px; }
  .itsm-status.ok { color:#15803d; } .itsm-status.fehler { color:#b91c1c; }
  .itsm-chips { display:flex; flex-wrap:wrap; gap:6px; align-items:center; border:1px solid #e2e8f0;
                border-radius:8px; padding:5px 6px; background:#fff; }
  .itsm-chips input { border:0 !important; flex:1 1 140px; min-width:120px; padding:4px !important; outline:none; }
  .itsm-chip { background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:999px;
               padding:2px 4px 2px 10px; font-size:.8rem; display:inline-flex; align-items:center; gap:2px; }
  .itsm-chip button { background:none; border:0; color:#64748b; cursor:pointer; font-size:1rem; line-height:1; padding:0 4px; }
  .itsm-aehnlich { font-size:.8rem; color:#92400e; background:#fffbeb; border:1px solid #fde68a; border-radius:8px;
                   padding:5px 8px; margin-top:5px; }
  .itsm-aehnlich button { background:none; border:0; color:#1d4ed8; text-decoration:underline; cursor:pointer;
                          font:inherit; padding:0 2px; }
  .itsm-aktionen { display:flex; gap:8px; justify-content:flex-end; margin-top:16px; flex-wrap:wrap; }
  .itsm-box button.itsm-btn, .itsm-tabelle button.itsm-btn, .itsm-filter button.itsm-btn {
      background:#2563eb; color:#fff; border:0; border-radius:8px; padding:8px 14px; font:inherit; font-weight:600; cursor:pointer; }
  .itsm-btn.sek { background:#fff !important; color:#2563eb !important; border:1px solid #2563eb !important; }
  .itsm-btn.gefahr { background:#fff !important; color:#dc2626 !important; border:1px solid #fca5a5 !important; }
  .itsm-btn.klein { padding:4px 10px !important; font-size:.8rem !important; }
  .itsm-btn:disabled { opacity:.5; cursor:wait; }
  .itsm-filter { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:10px;
                 font-size:.85rem; }
  .itsm-filter label { display:block; color:#64748b; font-size:.75rem; margin-bottom:2px; }
  .itsm-filter .itsm-check { display:flex; align-items:center; gap:6px; color:#334155; font-size:.85rem; padding-top:18px; }
  .itsm-filter .itsm-check input { width:auto; }
  .itsm-tabelle-wrap { overflow-x:auto; border:1px solid #e2e8f0; border-radius:10px; }
  .itsm-tabelle { width:100%; border-collapse:collapse; font-size:.85rem; background:#fff; }
  .itsm-tabelle th, .itsm-tabelle td { text-align:left; padding:7px 9px; border-bottom:1px solid #e2e8f0; vertical-align:top; }
  .itsm-tabelle th { color:#64748b; font-size:.72rem; text-transform:uppercase; font-weight:600; white-space:nowrap; background:#f8fafc; }
  .itsm-tabelle tr.gewaehlt td { background:#eff6ff; }
  .itsm-tabelle tr.archiviert td { color:#94a3b8; }
  .itsm-tabelle .itsm-name { font-weight:600; color:#1c2733; }
  .itsm-tabelle .itsm-beschr { color:#64748b; font-size:.78rem; }
  .itsm-tag { display:inline-block; background:#f1f5f9; border:1px solid #e2e8f0; border-radius:999px; padding:0 7px;
              font-size:.72rem; margin:1px 2px 1px 0; color:#475569; white-space:nowrap; }
  .itsm-index { font-size:.72rem; border-radius:999px; padding:1px 8px; white-space:nowrap; border:1px solid; }
  .itsm-index.bereit { color:#15803d; background:#f0fdf4; border-color:#bbf7d0; }
  .itsm-index.laeuft, .itsm-index.offen { color:#1d4ed8; background:#eff6ff; border-color:#bfdbfe; }
  .itsm-index.fehler, .itsm-index.veraltet { color:#b91c1c; background:#fef2f2; border-color:#fecaca; }
  .itsm-index.aus, .itsm-index.ohne_text { color:#64748b; background:#f8fafc; border-color:#e2e8f0; }
  .itsm-leer { color:#64748b; padding:14px; text-align:center; }
  .itsm-zusammenfassung { font-size:.8rem; color:#64748b; margin:6px 2px 0; }
  .itsm-vorschau { white-space:pre-wrap; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px;
                   max-height:220px; overflow:auto; font-size:.8rem; color:#334155; }
  .itsm-dl { display:grid; grid-template-columns:max-content 1fr; gap:4px 14px; margin:0; font-size:.85rem; }
  .itsm-dl dt { color:#64748b; } .itsm-dl dd { margin:0; word-break:break-word; }
  .itsm-meldung { margin-top:10px; padding:8px 12px; border-radius:0 8px 8px 0; font-size:.85rem; }
  .itsm-meldung.ok { border-left:4px solid #16a34a; background:#f0fdf4; }
  .itsm-meldung.fehler { border-left:4px solid #dc2626; background:#fef2f2; }
  @media (max-width: 640px) { .itsm-datei .itsm-zeile { grid-template-columns: 1fr; } .itsm-weg-sm { display:none; } }
  `;
  document.head.appendChild(stil);

  const esc = s => String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const schluessel = s => String(s || "").trim().replace(/\s+/g, " ").toLocaleLowerCase("de-CH");
  const datum = t => t ? new Date(t * 1000).toLocaleDateString("de-CH", { day: "2-digit", month: "2-digit", year: "numeric" }) : "–";
  const zeitpunkt = t => t ? new Date(t * 1000).toLocaleString("de-CH", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "–";
  function groesse(b) {
    if (b == null) return "–";
    if (b < 1024) return b + " B";
    if (b < 1024 * 1024) return (b / 1024).toFixed(0) + " KB";
    return (b / 1024 / 1024).toFixed(1).replace(".", ",") + " MB";
  }
  const zahl = n => n == null ? "–" : Number(n).toLocaleString("de-CH");
  const ICON = { pdf: "📕", docx: "📘", txt: "📄", md: "📄", png: "🖼️", jpg: "🖼️", jpeg: "🖼️" };
  const INDEX_TEXT = { bereit: "Index bereit", laeuft: "wird indexiert", offen: "Index offen", fehler: "Index-Fehler",
                       aus: "ohne Vektor-DB", ohne_text: "kein Text", veraltet: "anderes Modell" };

  async function api(pfad, opt = {}) {
    const r = await fetch("/api/teacher" + pfad, opt);
    if (r.status === 401) { location.href = "/teacher/login"; throw new Error("Bitte anmelden"); }
    let d = null;
    try { d = await r.json(); } catch { /* kein JSON */ }
    if (!r.ok) {
      const det = d && d.detail;
      const e = new Error(typeof det === "string" ? det : (det && det.message) || ("Fehler " + r.status));
      e.status = r.status; e.detail = det;
      throw e;
    }
    return d;
  }

  let wertCache = null;
  async function werte(neu) {
    if (!wertCache || neu) {
      try { wertCache = await api("/materialien/werte"); }
      catch { wertCache = { faecher: [], tags: [], niveaus: [], lehrpersonen: [], formate: [] }; }
    }
    return wertCache;
  }

  // Ähnliche, aber nicht gleiche Werte («Tier» neben «Tiere»): Hinweis statt Automatik.
  function abstand(a, b) {
    if (Math.abs(a.length - b.length) > 2) return 3;
    const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++)
      for (let j = 1; j <= b.length; j++)
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return d[a.length][b.length];
  }
  function aehnlich(wert, liste) {
    const k = schluessel(wert);
    if (k.length < 3) return null;
    for (const b of liste) {
      const kb = schluessel(b);
      if (kb === k) return null;
      if ((kb.length >= 4 && (kb.startsWith(k) || k.startsWith(kb))) || (k.length >= 4 && abstand(k, kb) <= 2)) return b;
    }
    return null;
  }
  function kanonisch(wert, liste) {
    const k = schluessel(wert);
    return liste.find(b => schluessel(b) === k) || String(wert || "").trim().replace(/\s+/g, " ");
  }

  let listenZaehler = 0;
  function datalist(werteListe) {
    const id = "itsm-dl-" + (++listenZaehler);
    const dl = document.createElement("datalist");
    dl.id = id;
    dl.innerHTML = werteListe.map(w => `<option value="${esc(w)}">`).join("");
    document.body.appendChild(dl);
    return id;
  }

  // Mehrere Werte (Fächer, Tags) als Chips mit Vorschlägen
  function chips(feld, vorschlaege, start, platzhalter) {
    const werteListe = [];
    const box = document.createElement("div");
    box.className = "itsm-chips";
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = platzhalter || "";
    input.setAttribute("list", datalist(vorschlaege));
    const hinweis = document.createElement("div");
    hinweis.className = "itsm-aehnlich";
    hinweis.hidden = true;
    feld.append(box, hinweis);
    function zeichnen() {
      box.querySelectorAll(".itsm-chip").forEach(c => c.remove());
      werteListe.forEach((w, i) => {
        const c = document.createElement("span");
        c.className = "itsm-chip";
        c.textContent = w;
        const x = document.createElement("button");
        x.type = "button"; x.textContent = "×"; x.title = "Entfernen";
        x.onclick = () => { werteListe.splice(i, 1); zeichnen(); };
        c.appendChild(x);
        box.insertBefore(c, input);
      });
    }
    function hinzufuegen(roh) {
      const w = kanonisch(roh, vorschlaege.concat(werteListe));
      if (!w) return;
      if (!werteListe.some(x => schluessel(x) === schluessel(w))) werteListe.push(w);
      const a = aehnlich(w, vorschlaege);
      if (a && !vorschlaege.some(v => schluessel(v) === schluessel(w))) {
        hinweis.innerHTML = `Ähnlicher Eintrag vorhanden: «${esc(a)}». <button type="button">«${esc(a)}» verwenden</button>`;
        hinweis.hidden = false;
        hinweis.querySelector("button").onclick = () => {
          const i = werteListe.findIndex(x => x === w);
          if (i >= 0) werteListe[i] = a;
          hinweis.hidden = true; zeichnen();
        };
      } else hinweis.hidden = true;
      zeichnen();
    }
    input.addEventListener("keydown", e => {
      if ((e.key === "Enter" || e.key === ",") && input.value.trim()) {
        e.preventDefault(); hinzufuegen(input.value); input.value = "";
      } else if (e.key === "Backspace" && !input.value && werteListe.length) {
        werteListe.pop(); zeichnen();
      }
    });
    input.addEventListener("change", () => {
      // Auswahl aus der Vorschlagsliste übernimmt den Wert sofort
      if (input.value.trim() && vorschlaege.some(v => v === input.value)) { hinzufuegen(input.value); input.value = ""; }
    });
    input.addEventListener("blur", () => { if (input.value.trim()) { hinzufuegen(input.value); input.value = ""; } });
    box.appendChild(input);
    (start || []).forEach(hinzufuegen);
    hinweis.hidden = true;
    return { get: () => { if (input.value.trim()) { hinzufuegen(input.value); input.value = ""; } return werteListe.slice(); },
             input };
  }

  // Ein Wert (Niveau) mit Vorschlägen
  function einzelwert(feld, vorschlaege, start, platzhalter) {
    const input = document.createElement("input");
    input.type = "text"; input.placeholder = platzhalter || ""; input.value = start || "";
    input.setAttribute("list", datalist(vorschlaege));
    const hinweis = document.createElement("div");
    hinweis.className = "itsm-aehnlich"; hinweis.hidden = true;
    feld.append(input, hinweis);
    input.addEventListener("blur", () => {
      input.value = kanonisch(input.value, vorschlaege);
      const a = input.value && !vorschlaege.some(v => schluessel(v) === schluessel(input.value)) && aehnlich(input.value, vorschlaege);
      if (a) {
        hinweis.innerHTML = `Ähnlicher Eintrag vorhanden: «${esc(a)}». <button type="button">«${esc(a)}» verwenden</button>`;
        hinweis.hidden = false;
        hinweis.querySelector("button").onclick = () => { input.value = a; hinweis.hidden = true; };
      } else hinweis.hidden = true;
    });
    return { get: () => kanonisch(input.value, vorschlaege), input };
  }

  function feld(parent, titel, hilfe) {
    const f = document.createElement("div");
    f.className = "itsm-feld";
    f.innerHTML = `<label>${esc(titel)}${hilfe ? ` <span class="itsm-hilfe">${esc(hilfe)}</span>` : ""}</label>`;
    parent.appendChild(f);
    return f;
  }

  function beschreibungFeld(parent, start) {
    const input = document.createElement("input");
    input.type = "text"; input.maxLength = BESCHREIBUNG_MAX; input.value = start || "";
    input.placeholder = "Kurz: Inhalt und Verwendung (höchstens 128 Zeichen)";
    const z = document.createElement("div");
    z.className = "itsm-zaehler";
    const zaehlen = () => {
      z.textContent = `${input.value.length}/${BESCHREIBUNG_MAX}`;
      z.classList.toggle("zu-lang", input.value.length > BESCHREIBUNG_MAX);
    };
    input.addEventListener("input", zaehlen); zaehlen();
    parent.append(input, z);
    return input;
  }

  function modal(inhalt) {
    const m = document.createElement("div");
    m.className = "itsm-modal";
    m.setAttribute("role", "dialog");
    m.setAttribute("aria-modal", "true");
    const box = document.createElement("div");
    box.className = "itsm-box";
    box.innerHTML = inhalt;
    m.appendChild(box);
    document.body.appendChild(m);
    return { m, box, schliessen: () => m.remove() };
  }

  let ich = null;
  async function wer() {
    if (!ich) {
      try { ich = await (await fetch("/api/me")).json(); } catch { ich = {}; }
    }
    return ich;
  }

  // ------------------------------------------------------------ Upload (L-01)
  async function uploadDialog(files, opt = {}) {
    files = Array.from(files || []);
    if (!files.length) return;
    const w = await werte(true);
    const me = await wer();
    const header = me && me.header_anmeldung && me.name;
    const { box, schliessen } = modal(`
      <h2>📥 Lernmaterial in die Ablage legen</h2>
      <p class="itsm-sub">Die Dateien stehen danach allen Lektionen zur Verfügung. Fächer, Niveau und Tags gelten
        für alle Dateien dieses Uploads; bestehende Einträge erscheinen als Vorschläge.</p>
      <div id="itsm-dateien"></div>
      <div id="itsm-gemeinsam"></div>
      <div class="itsm-aktionen">
        <button type="button" class="itsm-btn sek" id="itsm-abbr">Zurück, nichts hochladen</button>
        <button type="button" class="itsm-btn" id="itsm-los">Hochladen</button>
      </div>
      <div id="itsm-meldung"></div>`);
    const liste = box.querySelector("#itsm-dateien");
    const eintraege = files.map(f => {
      const d = document.createElement("div");
      d.className = "itsm-datei";
      d.innerHTML = `<div class="itsm-dname">${ICON[(f.name.split(".").pop() || "").toLowerCase()] || "📄"} ${esc(f.name)}
        <span class="itsm-hilfe" style="font-weight:400;color:#64748b">· ${groesse(f.size)}</span></div>
        <div class="itsm-zeile"><div><label class="itsm-hilfe">Name</label></div><div><label class="itsm-hilfe">Beschreibung</label></div></div>`;
      const zeile = d.querySelector(".itsm-zeile");
      zeile.innerHTML = "";
      const a = document.createElement("div"), b = document.createElement("div");
      a.innerHTML = '<label class="itsm-hilfe">Name</label>';
      b.innerHTML = '<label class="itsm-hilfe">Beschreibung (max. 128 Zeichen)</label>';
      const name = document.createElement("input");
      name.type = "text"; name.value = f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
      a.appendChild(name);
      const beschr = beschreibungFeld(b, "");
      zeile.append(a, b);
      const status = document.createElement("div");
      status.className = "itsm-status";
      d.appendChild(status);
      liste.appendChild(d);
      return { f, name, beschr, status, fertig: null };
    });
    const g = box.querySelector("#itsm-gemeinsam");
    const faecher = chips(feld(g, "Mögliche Fächer", "mehrere möglich, Enter fügt hinzu"), w.faecher, [], "z.B. Recht");
    const niveau = einzelwert(feld(g, "Lernendenprofil / Niveau", "Schätzung"), w.niveaus, "", "z.B. BM 2. Lehrjahr");
    const tags = chips(feld(g, "Tags", "mehrere möglich"), w.tags, [], "z.B. Haftung");
    let von = null;
    if (!header) {
      const fv = feld(g, "Hochgeladen von", "dein Name oder Kürzel, wird im Browser gemerkt");
      von = document.createElement("input");
      von.type = "text";
      try { von.value = localStorage.getItem("its_uploader") || ""; } catch { /* privat */ }
      von.setAttribute("list", datalist(w.lehrpersonen));
      fv.appendChild(von);
    } else {
      feld(g, "Hochgeladen von").insertAdjacentHTML("beforeend", `<div>${esc(me.name)} <span class="itsm-hilfe">(Anmeldung)</span></div>`);
    }
    eintraege[0].name.focus();
    box.querySelector("#itsm-abbr").onclick = () => { schliessen(); if (opt.onAbbruch) opt.onAbbruch(); };

    async function einzeln(e, trotzdem) {
      const fd = new FormData();
      fd.append("file", e.f);
      fd.append("name", e.name.value.trim());
      fd.append("beschreibung", e.beschr.value.trim());
      fd.append("faecher", JSON.stringify(faecher.get()));
      fd.append("niveau", niveau.get());
      fd.append("tags", JSON.stringify(tags.get()));
      if (von) fd.append("hochgeladen_von", von.value.trim());
      if (e.f.lastModified) fd.append("datei_geaendert_am", String(e.f.lastModified));
      if (trotzdem) fd.append("trotzdem", "true");
      return api("/materialien", { method: "POST", body: fd });
    }

    box.querySelector("#itsm-los").onclick = async () => {
      const los = box.querySelector("#itsm-los");
      for (const e of eintraege) {
        if (!e.fertig && e.beschr.value.length > BESCHREIBUNG_MAX) { e.beschr.focus(); return; }
        if (!e.fertig && !e.name.value.trim()) { e.name.focus(); return; }
      }
      if (von) { try { localStorage.setItem("its_uploader", von.value.trim()); } catch { /* privat */ } }
      los.disabled = true;
      for (const e of eintraege) {
        if (e.fertig) continue;
        e.status.className = "itsm-status";
        e.status.textContent = "Wird hochgeladen und gelesen …";
        try {
          e.fertig = await einzeln(e, false);
          e.status.className = "itsm-status ok";
          e.status.textContent = `✅ In der Ablage: ${zahl(e.fertig.zeichen)} Zeichen erkannt` +
            (e.fertig.seiten ? `, ${e.fertig.seiten} ${e.fertig.seiten === 1 ? "Seite" : "Seiten"}` : "") +
            (e.fertig.extraktion && e.fertig.extraktion.hinweis ? ". " + e.fertig.extraktion.hinweis : "");
        } catch (err) {
          if (err.status === 409 && err.detail && err.detail.vorhanden) {
            const v = err.detail.vorhanden;
            e.status.className = "itsm-status fehler";
            e.status.innerHTML = `${esc(err.message)} <button type="button" class="itsm-btn sek klein" data-a="nutzen">Vorhandenes verwenden</button>
              <button type="button" class="itsm-btn sek klein" data-a="trotzdem">Trotzdem neu hochladen</button>`;
            e.status.querySelector('[data-a="nutzen"]').onclick = () => {
              e.fertig = v; e.status.className = "itsm-status ok"; e.status.textContent = `✅ Vorhandenes Material «${v.name}» wird verwendet.`;
              fertigPruefen();
            };
            e.status.querySelector('[data-a="trotzdem"]').onclick = async () => {
              try { e.fertig = await einzeln(e, true); e.status.className = "itsm-status ok"; e.status.textContent = "✅ In der Ablage."; }
              catch (err2) { e.status.className = "itsm-status fehler"; e.status.textContent = "❌ " + err2.message; }
              fertigPruefen();
            };
          } else {
            e.status.className = "itsm-status fehler";
            e.status.textContent = "❌ " + err.message;
          }
        }
      }
      los.disabled = false;
      fertigPruefen();
    };
    function fertigPruefen() {
      const ok = eintraege.filter(e => e.fertig);
      if (ok.length === eintraege.length) {
        wertCache = null;
        schliessen();
        if (opt.onFertig) opt.onFertig(ok.map(e => e.fertig));
      } else if (ok.length) {
        const los = box.querySelector("#itsm-los");
        los.textContent = "Restliche nochmals versuchen";
        const weiter = box.querySelector("#itsm-weiter") || document.createElement("button");
        weiter.id = "itsm-weiter"; weiter.type = "button"; weiter.className = "itsm-btn sek";
        weiter.textContent = `Mit ${ok.length} ${ok.length === 1 ? "Datei" : "Dateien"} weiter`;
        weiter.onclick = () => { wertCache = null; schliessen(); if (opt.onFertig) opt.onFertig(ok.map(e => e.fertig)); };
        box.querySelector(".itsm-aktionen").insertBefore(weiter, los);
      }
    }
  }

  // ------------------------------------------------------------ Tabelle mit Filtern (L-02)
  function tabelle(container, opt = {}) {
    const auswahl = opt.modus === "auswahl";
    const gewaehlt = opt.gewaehlt || new Set();
    const gesperrt = opt.gesperrt || new Set();      // schon in der Lektion
    container.innerHTML = `
      <div class="itsm-filter">
        <div style="grid-column: span 2"><label>Suche (Name, Beschreibung, Datei)</label><input type="text" data-f="q" placeholder="Stichwort …"></div>
        <div><label>Fach</label><select data-f="fach"><option value="">alle</option></select></div>
        <div><label>Niveau</label><select data-f="niveau"><option value="">alle</option></select></div>
        <div><label>Tag</label><select data-f="tag"><option value="">alle</option></select></div>
        <div><label>Format</label><select data-f="format"><option value="">alle</option></select></div>
        <div><label>Hochgeladen von</label><select data-f="lehrperson"><option value="">alle</option></select></div>
        <div><label>Upload ab</label><input type="date" data-f="von"></div>
        <div><label>Upload bis</label><input type="date" data-f="bis"></div>
        ${auswahl ? "" : '<div class="itsm-check"><label class="itsm-check" style="padding:0"><input type="checkbox" data-f="archivierte"> Archivierte anzeigen</label></div>'}
      </div>
      <div class="itsm-tabelle-wrap"><table class="itsm-tabelle"><thead><tr>
        ${auswahl ? '<th style="width:28px"><input type="checkbox" data-alle title="Alle sichtbaren wählen"></th>' : ""}
        <th>Name</th><th>Fächer</th><th>Niveau</th><th>Tags</th><th class="itsm-weg-sm">Format</th>
        <th class="itsm-weg-sm">Seiten</th><th class="itsm-weg-sm">Grösse</th><th class="itsm-weg-sm">Datei geändert</th>
        <th>Hochgeladen</th><th class="itsm-weg-sm">Index</th>${auswahl ? "" : "<th>Lektionen</th><th></th>"}
      </tr></thead><tbody></tbody></table></div>
      <div class="itsm-zusammenfassung"></div>`;
    const tbody = container.querySelector("tbody");
    const filter = {};
    container.querySelectorAll("[data-f]").forEach(el => { filter[el.dataset.f] = el; });
    let daten = [];

    async function optionenLaden() {
      const w = await werte(true);
      const setzen = (sel, liste) => {
        const alt = sel.value;
        sel.innerHTML = '<option value="">alle</option>' + liste.map(v => `<option>${esc(v)}</option>`).join("");
        sel.value = alt;
      };
      setzen(filter.fach, w.faecher); setzen(filter.niveau, w.niveaus); setzen(filter.tag, w.tags);
      setzen(filter.format, w.formate); setzen(filter.lehrperson, w.lehrpersonen);
    }

    async function laden() {
      const p = new URLSearchParams();
      for (const [k, el] of Object.entries(filter)) {
        if (k === "archivierte") { if (el.checked) p.set(k, "true"); }
        else if (el.value.trim()) p.set(k, el.value.trim());
      }
      try { daten = await api("/materialien?" + p.toString()); }
      catch (e) { tbody.innerHTML = `<tr><td colspan="13" class="itsm-leer">${esc(e.message)}</td></tr>`; return; }
      zeichnen();
    }

    function zeichnen() {
      if (!daten.length) {
        tbody.innerHTML = `<tr><td colspan="13" class="itsm-leer">Keine Lernmaterialien${Object.values(filter).some(el => el.type === "checkbox" ? false : el.value) ? " zu diesen Filtern" : " in der Ablage"}.</td></tr>`;
      } else {
        tbody.innerHTML = daten.map(m => {
          const tags = l => (l || []).map(t => `<span class="itsm-tag">${esc(t)}</span>`).join("");
          const idx = m.index_status || "offen";
          const fest = gesperrt.has(m.id);
          return `<tr data-id="${esc(m.id)}" class="${gewaehlt.has(m.id) ? "gewaehlt" : ""} ${m.status === "archiviert" ? "archiviert" : ""}">
            ${auswahl ? `<td><input type="checkbox" data-w="${esc(m.id)}" ${gewaehlt.has(m.id) || fest ? "checked" : ""} ${fest ? 'disabled title="Schon in der Lektion"' : ""}></td>` : ""}
            <td><div class="itsm-name">${ICON[m.dateiformat] || "📄"} ${esc(m.name)}${m.status === "archiviert" ? ' <span class="itsm-tag">archiviert</span>' : ""}</div>
              <div class="itsm-beschr">${esc(m.beschreibung)}</div><div class="itsm-beschr">${esc(m.dateiname)}</div></td>
            <td>${tags(m.faecher)}</td><td>${esc(m.niveau || "")}</td><td>${tags(m.tags)}</td>
            <td class="itsm-weg-sm">${esc(m.dateiformat)}</td><td class="itsm-weg-sm">${m.seiten ?? "–"}</td>
            <td class="itsm-weg-sm">${groesse(m.dateigroesse)}</td><td class="itsm-weg-sm">${datum(m.datei_geaendert_am)}</td>
            <td title="${esc(zeitpunkt(m.hochgeladen_am))}">${datum(m.hochgeladen_am)}<div class="itsm-beschr">${esc(m.hochgeladen_von)}</div></td>
            <td class="itsm-weg-sm"><span class="itsm-index ${esc(idx)}" title="${esc((m.index_info && (m.index_info.fehler || m.index_info.modell)) || "")}">${esc(INDEX_TEXT[idx] || idx)}</span></td>
            ${auswahl ? "" : `<td>${m.lektionen_aktiv ? m.lektionen_aktiv : '<span class="itsm-beschr">keine</span>'}</td>
            <td style="white-space:nowrap"><button type="button" class="itsm-btn sek klein" data-a="details">Details</button>
              <a class="itsm-btn sek klein" style="text-decoration:none;display:inline-block" href="/api/teacher/materialien/${encodeURIComponent(m.id)}/datei">⬇</a>
              ${m.status === "archiviert"
                ? '<button type="button" class="itsm-btn sek klein" data-a="wiederherstellen">Wiederherstellen</button>'
                : `<button type="button" class="itsm-btn gefahr klein" data-a="archivieren" title="${m.lektionen_aktiv ? "Wird noch von einer aktiven Lektion verwendet" : "Entspricht dem Löschen, lässt sich wiederherstellen"}">Archivieren</button>`}</td>`}
          </tr>`;
        }).join("");
      }
      const n = daten.length;
      container.querySelector(".itsm-zusammenfassung").textContent =
        `${n} ${n === 1 ? "Lernmaterial" : "Lernmaterialien"}` + (auswahl ? ` · ${gewaehlt.size} gewählt` : "");
      if (auswahl) {
        const alle = container.querySelector("[data-alle]");
        const waehlbar = daten.filter(m => !gesperrt.has(m.id));
        alle.checked = waehlbar.length > 0 && waehlbar.every(m => gewaehlt.has(m.id));
      }
    }

    let warte = null;
    Object.values(filter).forEach(el => el.addEventListener(el.type === "text" ? "input" : "change", () => {
      clearTimeout(warte); warte = setTimeout(laden, el.type === "text" ? 200 : 0);
    }));
    container.addEventListener("change", e => {
      const id = e.target.dataset && e.target.dataset.w;
      if (id) {
        if (e.target.checked) gewaehlt.add(id); else gewaehlt.delete(id);
        zeichnen(); if (opt.onAuswahl) opt.onAuswahl(Array.from(gewaehlt));
      } else if (e.target.dataset && "alle" in e.target.dataset) {
        daten.filter(m => !gesperrt.has(m.id)).forEach(m => e.target.checked ? gewaehlt.add(m.id) : gewaehlt.delete(m.id));
        zeichnen(); if (opt.onAuswahl) opt.onAuswahl(Array.from(gewaehlt));
      }
    });
    tbody.addEventListener("click", async e => {
      const b = e.target.closest("button[data-a]");
      const tr = e.target.closest("tr[data-id]");
      if (!tr) return;
      const id = tr.dataset.id;
      if (auswahl && !b && e.target.tagName !== "INPUT" && !gesperrt.has(id)) {
        if (gewaehlt.has(id)) gewaehlt.delete(id); else gewaehlt.add(id);
        zeichnen(); if (opt.onAuswahl) opt.onAuswahl(Array.from(gewaehlt));
        return;
      }
      if (!b) return;
      if (b.dataset.a === "details") detailDialog(id, { onAenderung: () => { optionenLaden(); laden(); if (opt.onAenderung) opt.onAenderung(); } });
      if (b.dataset.a === "archivieren") archivieren(id, () => { laden(); if (opt.onAenderung) opt.onAenderung(); });
      if (b.dataset.a === "wiederherstellen") {
        try { await api(`/materialien/${encodeURIComponent(id)}/wiederherstellen`, { method: "POST" }); meldung("ok", "Lernmaterial wiederhergestellt."); }
        catch (err) { meldung("fehler", err.message); }
        laden(); if (opt.onAenderung) opt.onAenderung();
      }
    });
    function meldung(art, text) {
      let el = container.querySelector(".itsm-meldung");
      if (!el) { el = document.createElement("div"); container.insertBefore(el, container.firstChild); }
      el.className = "itsm-meldung " + art;
      el.textContent = text;
    }
    optionenLaden().then(laden);
    return { laden: () => optionenLaden().then(laden), gewaehlt, meldung, daten: () => daten };
  }

  function archivieren(id, danach) {
    const { box, schliessen } = modal(`<h2>Lernmaterial archivieren?</h2>
      <p>Archivieren entspricht dem Löschen: Das Material verschwindet aus der Ablage und lässt sich keiner
        Lektion mehr zuordnen. Datei, Text und Embeddings bleiben erhalten, du kannst es jederzeit
        wiederherstellen.</p>
      <div class="itsm-aktionen"><button type="button" class="itsm-btn sek" data-a="nein">Nein, behalten</button>
        <button type="button" class="itsm-btn gefahr" data-a="ja">Ja, archivieren</button></div><div class="itsm-m"></div>`);
    box.querySelector('[data-a="nein"]').onclick = schliessen;
    box.querySelector('[data-a="ja"]').onclick = async () => {
      try {
        await api(`/materialien/${encodeURIComponent(id)}/archivieren`, { method: "POST" });
        schliessen(); danach && danach();
      } catch (err) {
        const m = box.querySelector(".itsm-m");
        m.className = "itsm-meldung fehler";
        m.innerHTML = esc(err.message) + (err.detail && err.detail.lektionen
          ? "<br>" + err.detail.lektionen.map(l => `<a href="/teacher/lessons/${encodeURIComponent(l.id)}/edit">${esc(l.titel)}</a>`).join(" · ") : "");
        box.querySelector('[data-a="ja"]').disabled = true;
      }
    };
  }

  // ------------------------------------------------------------ Details und Bearbeiten
  async function detailDialog(id, opt = {}) {
    let m;
    try { m = await api(`/materialien/${encodeURIComponent(id)}`); } catch (e) { alert(e.message); return; }
    const w = await werte(true);
    const ix = m.index_info || {};
    const { box, schliessen } = modal(`
      <h2>${ICON[m.dateiformat] || "📄"} ${esc(m.name)}</h2>
      <p class="itsm-sub">${esc(m.dateiname)} · ${m.status === "archiviert" ? "archiviert" : "aktiv"}</p>
      <div id="itsm-meta"></div>
      <h3 style="font-size:.85rem;color:#64748b;text-transform:uppercase;margin:18px 0 6px">Datei</h3>
      <dl class="itsm-dl">
        <dt>Dateiname</dt><dd>${esc(m.dateiname)}</dd>
        <dt>Format</dt><dd>${esc(m.dateiformat)} (${esc(m.mime || "")})</dd>
        <dt>Grösse</dt><dd>${groesse(m.dateigroesse)}</dd>
        <dt>Seiten</dt><dd>${m.seiten ?? "–"}</dd>
        <dt>Datei geändert</dt><dd>${zeitpunkt(m.datei_geaendert_am)}</dd>
        <dt>Hochgeladen</dt><dd>${zeitpunkt(m.hochgeladen_am)} von ${esc(m.hochgeladen_von)}</dd>
        <dt>Speicherort</dt><dd><code>${esc(m.speicherort)}</code></dd>
        <dt>Text</dt><dd>${zahl(m.zeichen)} Zeichen (${esc((m.extraktion || {}).extraktor || "")})${(m.extraktion || {}).hinweis ? " – " + esc(m.extraktion.hinweis) : ""}</dd>
      </dl>
      <h3 style="font-size:.85rem;color:#64748b;text-transform:uppercase;margin:18px 0 6px">Vektordatenbank</h3>
      <dl class="itsm-dl">
        <dt>Stand</dt><dd><span class="itsm-index ${esc(m.index_status)}">${esc(INDEX_TEXT[m.index_status] || m.index_status)}</span>
          ${ix.fehler ? " " + esc(ix.fehler) : ""}</dd>
        ${ix.modell ? `<dt>Modell</dt><dd>${esc(ix.anbieter)} · ${esc(ix.modell)} · ${ix.dimension} Dimensionen · ${esc(ix.distanz || "")}</dd>
        <dt>Chunking</dt><dd>${zahl(ix.anzahl_chunks)} Chunks · bis ${zahl(ix.chunk_groesse)} Zeichen · Overlap ${zahl(ix.overlap)} Zeichen</dd>
        <dt>Indexiert</dt><dd>${zeitpunkt(ix.indexiert_am)}${ix.dauer_sekunden != null ? ` (${ix.dauer_sekunden} s)` : ""} · Sammlung <code>${esc(ix.sammlung || "")}</code></dd>` : ""}
      </dl>
      <div class="itsm-aktionen" style="justify-content:flex-start;margin-top:8px">
        <button type="button" class="itsm-btn sek klein" data-a="indexieren">Neu indexieren</button></div>
      <h3 style="font-size:.85rem;color:#64748b;text-transform:uppercase;margin:18px 0 6px">Verwendet in</h3>
      <div>${(m.lektionen || []).length ? m.lektionen.map(l => `<a href="/teacher/lessons/${encodeURIComponent(l.id)}/edit">${esc(l.titel)}</a>${l.archiviert ? " (archiviert)" : ""}`).join(" · ") : '<span class="itsm-beschr">keiner Lektion</span>'}</div>
      <h3 style="font-size:.85rem;color:#64748b;text-transform:uppercase;margin:18px 0 6px">Textvorschau</h3>
      <div class="itsm-vorschau" id="itsm-text">Wird geladen …</div>
      <div class="itsm-aktionen">
        <a class="itsm-btn sek" style="text-decoration:none" href="/api/teacher/materialien/${encodeURIComponent(m.id)}/datei">⬇ Originaldatei</a>
        <button type="button" class="itsm-btn sek" data-a="zu">Schliessen</button>
        <button type="button" class="itsm-btn" data-a="speichern">Metadaten speichern</button></div>
      <div class="itsm-m"></div>`);
    const meta = box.querySelector("#itsm-meta");
    const fn = feld(meta, "Name");
    const name = document.createElement("input"); name.type = "text"; name.value = m.name; fn.appendChild(name);
    const faecher = chips(feld(meta, "Mögliche Fächer"), w.faecher, m.faecher);
    const niveau = einzelwert(feld(meta, "Lernendenprofil / Niveau", "Schätzung"), w.niveaus, m.niveau);
    const beschr = beschreibungFeld(feld(meta, "Beschreibung", "höchstens 128 Zeichen"), m.beschreibung);
    const tags = chips(feld(meta, "Tags"), w.tags, m.tags);
    const ausgabe = box.querySelector(".itsm-m");
    api(`/materialien/${encodeURIComponent(id)}/text?max_zeichen=3000`).then(t => {
      box.querySelector("#itsm-text").textContent = t.seiten.map(s => (s.seite ? `— Seite ${s.seite} —\n` : "") + s.text).join("\n\n")
        + (t.gekuerzt ? "\n…" : "");
    }).catch(e => { box.querySelector("#itsm-text").textContent = e.message; });
    box.querySelector('[data-a="zu"]').onclick = schliessen;
    box.querySelector('[data-a="indexieren"]').onclick = async () => {
      try {
        await api(`/materialien/${encodeURIComponent(id)}/indexieren`, { method: "POST" });
        ausgabe.className = "itsm-meldung ok"; ausgabe.textContent = "Indexierung gestartet. Der Stand erscheint in der Liste.";
        if (opt.onAenderung) opt.onAenderung();
      } catch (e) { ausgabe.className = "itsm-meldung fehler"; ausgabe.textContent = e.message; }
    };
    box.querySelector('[data-a="speichern"]').onclick = async () => {
      try {
        await api(`/materialien/${encodeURIComponent(id)}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name.value, faecher: faecher.get(), niveau: niveau.get(),
                                 beschreibung: beschr.value, tags: tags.get() }),
        });
        wertCache = null;
        schliessen();
        if (opt.onAenderung) opt.onAenderung();
      } catch (e) { ausgabe.className = "itsm-meldung fehler"; ausgabe.textContent = e.message; }
    };
  }

  window.ITSMaterial = { uploadDialog, tabelle, detailDialog, api, groesse, zahl, datum, esc, ICON, INDEX_TEXT };
})();
