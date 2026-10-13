# ITS-MVP – Übergabe-Dokument für Claude

Dieses Dokument fasst den Stand des Projekts und die bisherige Zusammenarbeit
zusammen. Es dient als Kontext für eine neue Claude-Session (z.B. auf einem
anderen Rechner), damit dort ohne Unterbruch weitergearbeitet werden kann.
Lies zusätzlich das `README.md` im Projektstamm.

Stand: 13. Oktober 2026 (nachgeführt nach dem Auftrag «Anpassungen ITS-Prototyp nach dem
dritten Testdurchlauf», Pakete T-25, T-26 und D-13 bis D-18)

## 1. Projektkontext

Roy Franke (EB Zürich, roy.franke@gmx.ch) entwickelt im Rahmen des
DLH-Innovationsfonds-Projekts «Intelligente tutorielle Systeme erstellen mit KI»
einen ITS-Prototyp. Team: Roy Franke, Christian Flury (Systemkonzept),
Christian Hirt, Christian Roduner (Pilot-Lehrperson, BBW). Ziel: MVP bis
Dezember 2026, danach Pilotbetrieb in einer realen BM-Klasse.

Zentrale Konzeptdokumente (liegen im Claude-Projekt «ITS» als Wissen):
Systemkonzept von Christian Flury (April 2026, drei Ebenen Lektion /
Durchführung / Bearbeitung, Tutoring-Modi, Prinzip «Verlässlichkeit vor
Eloquenz», Lernpfade rekonstruierbar), Featureliste mit Milestones M1-M8,
Roadmap Juli-Dezember 2026, Roys MVP-Done-Kriterien, Pflichtenheft.

Wichtige Projektgeschichte: Im März 2026 gab es einen Reset. Der alte Prototyp
P1 wurde eingefroren; P2 ist eine RAG-Pipeline mit CLI auf dem Linux-System
RIB-AI-01 (GPU, On-Premise). Der hier entwickelte MVP ist ein Neuanfang per
Vibe Coding mit Claude.

## 2. Getroffene Entscheide

- MVP-Scope: Lernenden-Flow plus Lehrpersonen-Monitoring light, danach schrittweise erweitert.
- LLM-Abstraktion von Anfang an: Provider per `.env` umschaltbar (anthropic, openai, ollama, mock). On-Premise mit Ollama ist Must-Have für den Pilotbetrieb.
- Adaptionslogik bewusst als deterministischer Code, nicht als LLM-Entscheid (nachvollziehbar, testbar). Das LLM generiert Inhalte, Bewertungen, Feedback.
- Lektionen als austauschbare JSON-Dateien in `app/lessons/`, materialgebundener Systemprompt.
- Alles wird getestet (pytest) und in Git committet.

## 3. Aktueller Funktionsumfang

Lernenden-Flow: Onboarding mit Name und Lektionsauswahl, Wissenseinstufung
(3 KI-Fragen, Startniveau basic/intermediate/advanced mit Begründung),
adaptiver Lernpfad als Chat-Dialog. Adaption: richtig → weiter, 2 richtige in
Serie → Niveau rauf; falsch → Hinweis und zweiter Versuch, nochmals falsch →
Vereinfachung und Niveau runter. Theorie-Schritte (Lern-Input ohne Bewertung)
kommen adaptiv: auf basic vor jedem neuen Konzept, auf intermediate zum
Einstieg, nach zwei Fehlern als erneute einfachere Erklärung; nie zwei
automatische Theorie-Schritte nacheinander. Buttons «Theorie dazu», «Genauer
erklären», «Frage stellen» (unbewerteter Chat, verrät Lösung nicht).
Pausieren/Fortsetzen über localStorage plus DB-Zustand. Abschlussbilanz mit
Lernzielabgleich.

Nach LLMTutor-Vorbild (Swiss Learning Analytics, siehe Abschnitt 6):
dreistufige Bewertung korrekt/teilweise/falsch (teilweise → Wahl zwischen
Ergänzen, Lösung ansehen und Weiter, seit D-07; zählt weder als Fehler noch als richtig) und Sicherheitsfrage 1-10 vor der ersten Bewertung jeder Aufgabe
(protokolliert, Durchschnitt in der Teacher-Übersicht).

Lehrpersonen: Monitoring unter `/teacher` (Sessionübersicht mit Fortschritt,
Niveau, Quote, Sicherheit; vollständiger Lernverlauf pro Session aus dem
Event-Log). Lektionseditor unter `/teacher/lessons/new`: Material einfügen
oder hochladen (PDF/Word/Text, Textextraktion), KI-Vorschlag für Titel und
Lernziele, Tutor-Hinweise, speichern → sofort verfügbar.

Technisch: FastAPI (Python), SQLite (Sessions + Event-Log, vollständige
Protokollierung, Migrationen beim Start in `store._migrate`), Vanilla-JS-Frontend
(5 statische Seiten), KaTeX für Formeldarstellung (LaTeX-Anweisung im
Systemprompt), Diagnose-Endpoint `/api/llm-test` (nur Lehrpersonen), rund 270
pytest-Tests (seit Oktober 2026 rund 500). Mock-Provider bewertet heuristisch nach Antwortlänge (>=40 Zeichen
korrekt, 15-39 teilweise, sonst falsch), damit die Adaption ohne LLM
demonstrierbar ist; `ITS_MOCK_DELAY` und `ITS_MOCK_FAIL` simulieren langsame
oder scheiternde Aufrufe für Oberflächentests.

Seit dem Auftrag «Anpassungen ITS-Prototyp» (September 2026) zusätzlich:
Rollen «lernend»/«lehrperson» zentral in `app/auth.py` (Router-Abhängigkeiten,
optional Anmeldung über Proxy-Header), Lernsequenzen pro Person mit Status
(aktiv, pausiert, abgeschlossen, abgebrochen, archiviert) und optionaler PIN,
Buttons Pausieren/Abbrechen, Lektionsverwaltung unter `/teacher/lessons` mit
Tutor-Einstellungen pro Lektion (`app/einstellungen.py`), Regelkatalog
`app/didaktik.py` mit deterministischen Prüfungen nach der Generierung
(Lösungswort, Theorie-Beispiel, Abschreibbarkeit, unerklärte Konzepte,
Ähnlichkeit, Ton), Eskalation bei Nachfragen, Niveausteuerung mit Zustimmung,
Bewertung in zwei Schritten mit Elementen, Materialprüfung im Editor.
Details pro Paket in den Statusnotizen `claude/status-*.md` im Claude-Projekt.

Phase 4 (28.9.2026): Quellenzeile unter Theorieschritten mit Prüfung gegen die
«### Quelle:»-Blöcke (N-01), Lehrpersonen-Sicht mit Seitenleiste, Filtern und
Zeitleiste (N-02), Internetrecherche als dritte Wissensstufe über SearXNG,
global mit `ITS_WEB_SEARCH` abschaltbar und standardmässig aus (N-03, Modul
`app/websuche.py`), Rückmeldung zur Selbsteinschätzung und Kalibrierung
(N-04), eigener Lernverlauf für Lernende über eine Whitelist aus dem Event-Log
(N-05, `tutor.verlauf_fuer_lernende`). Bewertung läuft mit Temperatur 0.

Auftrag 2 (11.10.2026, Feedback vom 29.9.2026): Promptlänge wird vor jedem
Ollama-Aufruf gegen `OLLAMA_NUM_CTX` geschätzt und bei Überschreitung im Log,
im Fallback-Event und im Editor gemeldet (T-08). Leere Modellantworten sind ein
eigener Fehlerfall mit done_reason und Tokenzahlen; der zweite Versuch läuft
ohne format=json (T-09). Alle LLM-Antworten werden auf Felder und Typen geprüft,
Einstufungsfragen als Objekte werden gerettet (T-10). Statt Schleifen und
Lückenbüssern bietet der Tutor Wahlmöglichkeiten über den neuen Endpunkt
`/wahl` an: nach gescheiterter Bewertung (T-11), nach einem Fallback inklusive
«Witz zum Thema» (T-12) und nach teilweise richtiger Antwort (D-07, Entscheid
E1: zählt weder als Fehler noch als richtig). Tutor-Texte werden mit einer
kleinen Markdown-Teilmenge dargestellt (`static/format.js`, T-13). Beim
Fortsetzen erscheint der ganze Dialog (T-14). Didaktik: keine doppelte Theorie
dank Kernbegriff-Vergleich und Ähnlichkeitsprüfung (D-08), Aufgabe passt zur
vorangehenden Theorie (D-09), erwartete Elemente entstehen mit der Aufgabe und
die Bewertung prüft nur diese (D-10), kopierte Antworten werden nicht bewertet
(D-11), Urteil und Bewertungstext müssen zusammenpassen (D-12). Lehrpersonen:
Lektion duplizieren (T-17), Titel als Pflichtfeld und Lernziel-Vorschlag als
experimentell (T-18), klare Meldung der Materialprüfung (T-19), Archivieren und
Wiederherstellen von Sequenzen und Lektionen (T-20). Betrieb: Abmelden auf allen
Seiten über `/logout` (T-22), Abmelden beim Proxy über `X-Logout-Url` bzw.
`ITS_LOGOUT_URL` (T-23), Header-Debug-Logging mit `ITS_LOG_LEVELS=its.auth=DEBUG`
(T-24). Details und gefundene Ursachen in den Statusnotizen
`claude/status-t08-…` bis `claude/status-t24-…`, `claude/status-d07-…` bis
`claude/status-d12-…` und `claude/status-auftrag-2.md`.

Auftrag 3 (13.10.2026, Feedback von Christian zum Test mit «Haftungsrecht: Unerlaubte
Handlungen Version 3»): Im Zentrum steht das Prinzip «Verlässlichkeit vor Eloquenz».
Neue Bewertungslogik: Erwartete Elemente sind Objekte `{dimension, erwartet}` (alte Texte
gelten als Dimension ohne Inhalt). Element-Status `korrekt`, `vertretbar` (zählt wie korrekt,
mit `annahme`), `ungenau`, `nicht_beurteilbar` (zählt wie ungenau; nur in Lektionen ohne
Allgemeinwissen), `falsch` (nur Widerspruch zu Sachverhalt oder Material), `fehlt`; jedes
Element trägt `begruendung` und `antwort` (Zitat). Nachbesserungen werden als neuester Stand
bewertet, mit dem Elementstatus der letzten Bewertung im Prompt (D-14). Neue Aufgaben
nennen `merkmale` mit Fundstelle im Fall, `alternative_loesungen` und werden gegengeprüft
(`tutor.pruefe_musterloesung`, Schrittarten `MUSTERLOESUNG_PRUEFEN` und
`MUSTERLOESUNG_VERGLEICHEN`, Feld `musterloesung_pruefung` mit `offene_punkte`, D-13).
Neubewertungen ohne Versuch über `main._neu_bewerten`: Widerspruch der lernenden Person
(D-15), Selbstkorrektur des Tutors im Chat (D-18); Urteilskorrektur bei «Lösung ansehen»
(D-17). Zusätzliche Buttons kommen als `zusatz` neben `wahl` (`tutor.zusatz_wahl`). Neue
Ereignisse: `musterloesung_geprueft`, `alternative_anerkannt`, `widerspruch_lernende`,
`tutor_korrektur`, `tutor_neubewertung`, `urteil_korrigiert`, `abschwaechung_warnung`.
Oberfläche: Legende passend zu den sichtbaren Buttons (T-25), Zeitstempel in der
Sequenzliste (T-26). Details in `claude/status-t25-…` bis `claude/status-d18-…` und
`claude/status-auftrag-3.md`.

Prüfwerkzeuge neben pytest: `tests/ui/ui_checks.py` (Playwright gegen eine
eigens gestartete Instanz) und `tests/eval/eval_didaktik.py` (Evaluation der
didaktischen Pakete gegen das echte Modell, schreibt einen Bericht nach
`tests/eval/berichte/`).

## 4. Setup auf einem neuen Rechner

```bash
git clone <REPO-URL>          # Repo liegt auf Roys GitHub-Account, Name: its-mvp
cd its-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # Provider eintragen, siehe unten
uvicorn app.main:app --reload
# Browser: http://localhost:8000  |  /teacher  |  /api/info  |  /api/llm-test
# Tests: python3 -m pytest tests/ -q
```

`.env` auf Roys MacBook: `LLM_PROVIDER=ollama`, `OLLAMA_MODEL=qwen2.5:7b`.
Auf a9-mega (Ryzen AI Max+ 395, Radeon 8060S, 64 GB nutzbarer Grafikspeicher):
`OLLAMA_MODEL=qwen3:30b` (MoE, laeuft zu 100 % auf der GPU), `OLLAMA_NUM_CTX=16384`,
`OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_THINK=false`. Der Denkmodus ist bewusst aus:
Qwen3 braucht mit Denken rund 11 Sekunden selbst fuer eine Ein-Wort-Antwort
(ohne Denken 3,3 Sekunden, gemessen ueber /api/llm-test auf a9-mega),
und der Gedankengang wird ohnehin verworfen (`strip_reasoning` in `llm.py`).
Fuer Qualitaetsvergleiche laesst er sich mit `OLLAMA_THINK=true` einschalten.
Zugänge (API-Keys, GitHub-Token) stehen bewusst NICHT in diesem Dokument –
die `.env` ist gitignored und wird pro Rechner neu erstellt.

## 4b. Antwortzeiten im Dialog

Die gefuehlte Wartezeit entsteht an drei Stellen, und nur eine davon ist das Modell selbst.

**Messen zuerst.** Jeder LLM-Aufruf wird mitgeschrieben und erscheint im
Lehrpersonen-Monitoring unter «Antwortzeiten des Sprachmodells» (Rohdaten unter
`/api/teacher/timings`, nur im Arbeitsspeicher, nach einem Neustart leer). Interessant
ist die Aufteilung in der Fussnote: Ist `prompt_sekunden` hoch, kostet die Verarbeitung
des Lektionsmaterials; ist `tokens_pro_sekunde` niedrig, ist das Modell zu gross fuer
die Maschine.

**Wartezeit verstecken.** Das Frontend erzeugt den naechsten Schritt bereits, waehrend
der Lernende das Feedback oder den Theorie-Text liest (`prefetchNext` in `index.html`).
Beim Klick auf «Weiter» liegt die Antwort meist schon vor. Nach einer Nachbesserung
(`retry`) wird bewusst nicht vorgeladen, weil dort offen ist, wie es weitergeht.

Nebenwirkung: Waehrend die Vorab-Anfrage laeuft, stellt sich eine Verstaendnisfrage bei
`OLLAMA_NUM_PARALLEL=1` hinten an. Mit `OLLAMA_NUM_PARALLEL=2` laufen beide gleichzeitig,
zum Preis eines zweiten Kontextfensters im Speicher — auf a9-mega mit 64 GB unproblematisch.

**Systemprompt nicht pro Schrittart kuerzen.** Ollama behaelt den gemeinsamen Anfang
einer Anfrage im Cache. Weil `_system_prompt` fuer alle Schritte derselben Lektion
identisch ist, faellt die Verarbeitung des Materials nur beim ersten Aufruf einer Session
richtig ins Gewicht. Wer das Material je nach Schritt beschneidet, zerstoert genau diesen
Effekt und macht es insgesamt langsamer.

**Weitere Stellschrauben**, falls die Messung zeigt, dass es am Modell liegt:
`OLLAMA_NUM_PREDICT` begrenzt Ausreisser nach oben, `OLLAMA_FLASH_ATTENTION=1` und
`OLLAMA_KV_CACHE_TYPE=q8_0` verkleinern den Speicherbedarf des Kontextfensters, und erst
danach lohnt sich der Versuch mit einem kleineren Modell.

## 5. Bekannte Stolpersteine (alle schon erlebt)

- `.env` wird nur beim Serverstart gelesen; nach Änderungen uvicorn neu starten.
- Befehle immer im Projektordner ausführen (`cd its-mvp`), venv aktivieren; auf Roys MacBook existiert zusätzlich ein verirrtes `.venv` im Home-Verzeichnis.
- Ollama: Menüleisten-App muss laufen (sonst «Connection refused» auf Port 11434); `OLLAMA_MODEL` muss exakt einem Eintrag aus `ollama list` entsprechen.
- Fallbacks sind seit T-01 sichtbar: Im Lernverlauf als «Fallback» markiert mit Grund, in der Tabelle der Antwortzeiten als Spalte «Fallbacks». Bei vielen Fallbacks `/api/llm-test` aufrufen (als Lehrperson angemeldet).
- Der Systemprompt muss innerhalb einer Lektion für alle Schrittarten identisch bleiben (Prompt-Cache). Schrittbezogenes (gezeigte Theorie, erklärte Konzepte, Beispiele) gehört in den Benutzerteil; ein Test prüft das.
- Der Server schreibt beim Start ins Fenster, welcher Zugangsschutz aktiv ist. Windows-Umgebungsvariablen haben Vorrang vor der `.env`.
- Frontend-Änderungen brauchen einen Hard-Refresh (Cmd+Shift+R).
- KaTeX lädt vom CDN; für Betrieb ohne Internet lokal bundeln.
- Roys OpenAI-Key wurde einmal im Chat geteilt und sollte rotiert werden (platform.openai.com).
- Material, das ohne Zeilenumbrüche eingefügt wurde («EinstiegFür»), klebt in der Anzeige zusammen. «Material prüfen» meldet das seit T-13; das Material der Quantenphysik-Lektion ist gegliedert.
- Sehr grosses Material (ganzes OR) sprengt das Kontextfenster: Ollama kürzt still. Seit T-08 warnen Log, Lernverlauf und Editor; die Lösung ist kürzeres Material oder später RAG.
- Leere Antworten von qwen3:30b (T-09, belegt am 12.10.2026): Fehlt im Aufruf das Feld `think`, denkt das Modell bis `OLLAMA_NUM_PREDICT` und liefert nichts (12 von 12 leer). Deshalb `OLLAMA_THINK=false` nie leer lassen. Das ITS wiederholt solche Aufrufe sofort mit think=false. Ohne format=json schreibt das Modell bis zum Limit; der JSON-Modus bleibt deshalb auch im zweiten Versuch eingeschaltet. Steht die Antwort im Feld thinking, wird sie von dort gelesen.
- Ohne `TEACHER_PASSWORD` gilt jede Anfrage als Lehrperson. Nach «Abmelden» verhindert ein Merker-Cookie das sofortige Zurückleiten (T-22); «Anmelden» auf der Login-Seite geht dann ohne Passwort.
- Angemeldete Lernende erhalten auf Lehrpersonen-Endpunkten seit T-20 den Status 403 (ohne Anmeldung weiterhin 401).
- Neue Wartezustände in `profile.wartet_auf`: `bewertung_wiederholen`, `wahl_unbewertet`, `wahl_fallback`, `wahl_teilweise` (alte Sessions mit `nochmals` funktionieren weiter).
- Seit Auftrag 3 kostet eine neue Aufgabe mindestens einen zusätzlichen LLM-Aufruf (Gegenprüfung), bei abweichenden Fachbegriffen zwei, bei einer Abweichung zusätzlich eine Neugenerierung. Das läuft im Vorabruf; klickt jemand sehr schnell auf «Weiter», wird die Wartezeit sichtbar. In der Messübersicht stehen die Zeilen «Musterlösung prüfen» und «Musterlösung vergleichen». Notfalls `ITS_MUSTERLOESUNG_PRUEFEN=false`.
- Die Bewertung spricht von der «erwarteten Lösung», nicht mehr von der «Musterlösung»; ein Feedback, das die Musterlösung erwähnt, gilt als Regelverstoss (D-14).
- `profile.antworten_aktuell` enthält seit D-14 auch die Elemente der letzten Bewertung. Neubewertungen (Widerspruch, Selbstkorrektur, Urteilskorrektur) nehmen die Zählung der ersetzten Bewertung zurück (`main._urteil_zuruecknehmen`); sie sind nur bei offener Aufgabe möglich.
- Der Mock-Provider kennt die neuen Schrittarten. «stimmt doch», «vertretbar» oder «Annahme» in einem Widerspruch lassen ihn das Urteil ändern, «wirklich» in einer Verständnisfrage nach einer Bewertung löst eine Selbstkorrektur aus (für Playwright).

## 6. Austausch mit Swiss Learning Analytics (LLMTutor)

github.com/SwissLearningAnalytics/LLMTutor – Open-Source-LLM-Tutor aus dem
BeLEARN-Projekt, fallbasiert-sokratisch, drehbuchbasiert (YAML mit grossem
Systemprompt inkl. Musterlösungen), TypeScript/Postgres, Hochschulkontext.
Es besteht ein Austausch mit den Verantwortlichen (Kontakt:
borter@learning-analytics.ch). Komplementär: Ihr Autoren-Engpass (YAML von
Hand) vs. unser Lektionseditor; ihre didaktische Präzision vs. unsere
Adaptivität. Bereits übernommen: dreistufige Bewertung, Feedback-Regeln,
Sicherheitsfrage. Ideen für Zusammenarbeit: Log-Formate abstimmen (ihr
Folgeprojekt erforscht Muster erfolgreichen Lernens), Autorenwerkzeug für
ihre YAML-Tutoren, gemeinsame Evaluationsinstrumente für den Pilot.

## 7. Nächste Schritte (besprochen und priorisiert)

1. **Klassentest-Block – UMGESETZT (27.8.2026)**: Lehrpersonen-Login (`TEACHER_PASSWORD`, signiertes Cookie, Login-Seite `/teacher/login`, Logout; Passwortwechsel invalidiert alte Logins), Zugangscode für Lernende (`CLASS_CODE`, Prüfung beim Session-Start, Pseudonym-Hinweis im Onboarding), Deployment-Paket (Dockerfile, docker-compose mit Caddy/HTTPS, `docs/DEPLOYMENT.md` mit VPS-Anleitung für Infomaniak). Auth-Logik in `app/auth.py`, Secret in der DB (Tabelle `config`), 11 neue Tests in `tests/test_auth.py`. Leere Variablen deaktivieren den Schutz (lokale Entwicklung); in Roys lokaler `.env` auf a9-mega sind Testwerte gesetzt (`teste-mich` / `BM2026`). Veröffentlichung umgesetzt via Cloudflare Tunnel (28.8.2026): Betrieb lokal auf a9-mega, extern erreichbar unter https://tutor.casaai.me (Domain casaai.me liegt in Roys Cloudflare-Account; cloudflared als Windows-Dienst, Anleitung in `docs/DEPLOYMENT-CLOUDFLARE.md`). Zugangsdaten (TEACHER_PASSWORD, CLASS_CODE) stehen nur in der lokalen `.env`. Setup steht seit dem 28.8.2026 und funktioniert: ein dashboard-verwalteter
Tunnel `a9-mega` mit zwei Routen (tutor.casaai.me → localhost:8010 für das ITS,
ollix-free.casaai.me → localhost:8000 für Roys andere Anwendung), cloudflared
als Windows-Dienst. Das ITS läuft neu auf Port 8010, festgelegt in `start.bat`,
weil Port 8000 von der anderen Anwendung belegt ist. Merksatz: Pro Rechner
genau ein Tunnel und ein cloudflared-Dienst; weitere Anwendungen kommen als
zusätzliche Routen mit eigenem Port dazu, nicht als zweiter Tunnel.
Noch offen: gleiches Tunnel-Muster später für RIB-AI-01 im Pilot.
2. **Anpassungen aus dem ersten Testdurchlauf – Phasen 1 bis 4 UMGESETZT (27./28.9.2026)**: T-01 bis T-07, D-01 bis D-06 und N-01 bis N-05. Evaluation mit qwen3:30b gelaufen (Berichte unter `tests/eval/berichte/`, Befunde in den Statusnotizen D-01 und D-05). Offen: Klassentest mit echtem Modell, Material der Quantenphysik-Lektion überarbeiten (D-06), für die Internetrecherche einen SearXNG-Dienst aufsetzen. Kandidat für später: Bewertungselemente schon bei der Aufgabengenerierung festlegen statt bei jeder Bewertung neu (siehe D-05).
3. **Anpassungen aus dem zweiten Testdurchlauf – UMGESETZT (11.10.2026)**: T-08 bis T-24, D-07 bis D-12, 495 pytest-Tests und 152 Playwright-Prüfungen grün. Evaluation und Diagnose gegen qwen3:30b am 12.10.2026 auf a9-mega gelaufen: alle Kriterien D-07 bis D-12 erfüllt, 0 Fallbacks und 0 leere Antworten bei rund 200 Aufrufen; Ursache der leeren Antworten belegt, Tokenschätzung kalibriert (3.4 Zeichen pro Token). Offen: Klassentest. Ausblick laut Auftrag: lektionsspezifische Witze im Editor, Wahl auch nach falscher Antwort, automatisches Kürzen oder RAG für grosses Material.
3b. **Anpassungen aus dem dritten Testdurchlauf – UMGESETZT (13.10.2026)**: T-25, T-26, D-13 bis D-18 nach den Entscheiden E1 bis E6 (Vorschläge), pytest und Playwright grün. Offen: Evaluation mit qwen3:30b auf a9-mega (`tests/eval/eval_didaktik.py D-13 D-14 D-15 D-16 D-17 D-18 T-09`), Auswertung von Christians its.db vom 13.10.2026 und der Lektion «Haftungsrecht Version 3». Ausblick laut Auftrag: Musterlösungen durch die Lehrperson korrigieren, Auswertung pro Lektion nach Widerspruch, Selbstkorrekturen und unsicheren Musterlösungen, geprüfte Fallaufgaben für normative Fächer.
4. **Prompt-Tuning** mit Roys Praxisbeobachtungen auf Basis der Evaluationsberichte (Vergleich Ollama vs. Cloud als Evaluationsergebnis).
5. **Tutoring-Modi** (erklärend, sokratisch, prüfend, coaching) aus dem Systemkonzept; sokratische Hinweis-Treppe von LLMTutor als Vorlage.
6. Später: RAG-Anbindung an P2 für grosse Materialmengen, KaTeX lokal bundeln, Klassenverwaltung.

## 8. Arbeitsweise in der Zusammenarbeit

Roy ist Lehrperson, kein Entwickler; Terminal-Anleitungen konkret und
schrittweise geben (cd in Projektordner, venv aktivieren, Server-Fenster offen
lassen). Deutsch mit Schweizer Rechtschreibung, Du-Form, Fliesstext, keine
KI-Floskeln. Nach jeder Änderung: Tests laufen lassen, End-to-End-Smoke-Test,
README nachführen, Git-Commit mit deutscher Message. Roy testet selbst im
Browser und meldet Beobachtungen, oft mit Screenshots.
