/* Formatierung der Tutor-Texte (T-13, Entscheid E7).
 *
 * Erlaubt ist eine kleine Teilmenge von Markdown: Absätze (Leerzeile),
 * Zwischentitel (# bis ####), Aufzählungen (- * •), nummerierte Listen (1. 2.)
 * und Fettdruck (**…**). Keine Links, Bilder, Tabellen oder HTML.
 *
 * Sicherheit: Der ganze Text wird zuerst maskiert, erst danach werden die
 * erlaubten Formatierungen als Tags eingesetzt. HTML aus Modellantworten kann
 * so nie ausgeführt werden. Formeln in $…$, $$…$$, \(…\), \[…\] bleiben
 * unangetastet, damit KaTeX sie danach setzen kann.
 *
 * Gemeinsam genutzt von index.html (Chat, eigener Verlauf, Abschluss) und
 * teacher.html (Lernverlauf der Lehrperson).
 */
(function () {
  "use strict";

  function maskiere(s) {
    return String(s ?? "").replace(/[&<>"']/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // Formelbereiche nicht anfassen: Fettdruck nur ausserhalb davon
  const FORMEL = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])/g;

  function inline(text) {
    return maskiere(text).split(FORMEL).map((teil, i) =>
      i % 2 === 1 ? teil : teil.replace(/\*\*(?=\S)([^*]+?)\*\*/g, "<strong>$1</strong>")
    ).join("");
  }

  const TITEL = /^\s{0,3}#{1,4}\s+(.+?)\s*#*\s*$/;
  const PUNKT = /^\s*[-*•]\s+(.*)$/;
  const NUMMER = /^\s*(\d{1,3})[.)]\s+(.*)$/;

  function html(text) {
    const zeilen = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
    const out = [];
    let absatz = [], liste = null;           // liste: { tag, start, punkte }

    const absatzAbschliessen = () => {
      if (absatz.length) out.push("<p>" + absatz.map(inline).join("<br>") + "</p>");
      absatz = [];
    };
    const listeAbschliessen = () => {
      if (!liste) return;
      const start = liste.tag === "ol" && liste.start !== 1 ? ` start="${liste.start}"` : "";
      out.push(`<${liste.tag}${start}>` + liste.punkte.map(p => "<li>" + inline(p) + "</li>").join("") +
               `</${liste.tag}>`);
      liste = null;
    };

    for (const zeile of zeilen) {
      if (!zeile.trim()) { absatzAbschliessen(); listeAbschliessen(); continue; }
      let m;
      if ((m = zeile.match(TITEL))) {
        absatzAbschliessen(); listeAbschliessen();
        out.push('<h4 class="fmt-titel">' + inline(m[1]) + "</h4>");
      } else if ((m = zeile.match(PUNKT)) && !/^\s*\*\*/.test(zeile)) {
        absatzAbschliessen();
        if (!liste || liste.tag !== "ul") { listeAbschliessen(); liste = { tag: "ul", punkte: [] }; }
        liste.punkte.push(m[1]);
      } else if ((m = zeile.match(NUMMER))) {
        absatzAbschliessen();
        if (!liste || liste.tag !== "ol") { listeAbschliessen(); liste = { tag: "ol", start: +m[1], punkte: [] }; }
        liste.punkte.push(m[2]);
      } else if (liste && /^\s{2,}\S/.test(zeile)) {
        // eingerückte Fortsetzung des letzten Listenpunkts
        liste.punkte[liste.punkte.length - 1] += " " + zeile.trim();
      } else {
        listeAbschliessen();
        absatz.push(zeile.trim());
      }
    }
    absatzAbschliessen();
    listeAbschliessen();
    return out.join("");
  }

  /* Setzt den formatierten Text in ein Element (ersetzt dessen Inhalt nicht,
   * sondern hängt einen Block an, damit z.B. eine «who»-Zeile erhalten bleibt). */
  function anhaengen(el, text) {
    const div = document.createElement("div");
    div.className = "fmt";
    div.innerHTML = html(text);
    el.appendChild(div);
    return div;
  }

  window.ITSFormat = { html, anhaengen, maskiere };
})();
