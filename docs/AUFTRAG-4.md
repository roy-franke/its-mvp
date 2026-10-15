# Auftrag 4: Lernmaterialien, RAG, Stopp, Favicon, Versionierung

Grundlage: Feedback von Pascal zum Prototyp vom 13.10.2026 («Prototyp_Roy_2026-10-15_Feedback.docx»).
Dieses Dokument hält fest, wie der Auftrag gelesen, wo er ergänzt und was entschieden wurde.
Der Umsetzungs- und Ergebnisbericht beruht darauf.

## 1. Pakete und Priorität

| Paket | Thema (Feedback) | Priorität |
|---|---|---|
| L-01 | Lernmaterialien global verfügbar und um Metadaten erweitert (Lehrpersonen-Teil 1) | Must |
| L-02 | Für Lektion globale Lernmaterialien auswählen (Lehrpersonen-Teil 2) | Must |
| L-03 | Löschen/Archivieren von Lernmitteln (Lehrpersonen-Teil 3) | Must |
| T-27 | Favicon (Technischer Teil 1) | Must |
| T-28 | Bearbeitung einer Anfrage stoppen (Technischer Teil 2) | Nice |
| T-29 | Lernmaterialien als Embeddings in einer Vektordatenbank (Technischer Teil 3) | Should |
| T-30 | Embeddings im Chat-Prozess verwenden, RAG (Technischer Teil 4) | Should |
| T-31 | Versionierung einführen und anzeigen (Technischer Teil 5) | Must |

Punkt 2a (Freitextsuche über die Vektordatenbank bei der Auswahl) ist im Feedback gestrichen und
wird nicht umgesetzt.

## 2. Ergänzungen und Auslegung

**L-01.** Upload an zwei Orten: auf der neuen Seite «Lernmaterialien» (`/teacher/materialien`) und
wie bisher im Lektionseditor. Jede hochgeladene Datei wird zu einem globalen Lernmaterial; das
frühere lektionsinterne Hochladen entfällt. Metadaten: Name (Pflicht, Vorschlag aus dem
Dateinamen), mögliche Fächer (mehrere), Niveau (ein Wert, Schätzung), Beschreibung (höchstens 128
Zeichen, auf Client und Server geprüft), Tags (mehrere). Vorschläge kommen aus den Werten aller
Lernmaterialien. Gegen Dubletten wirkt zusätzlich der Server: Ein Wert, der sich von einem
bestehenden nur in Gross-/Kleinschreibung oder Leerzeichen unterscheidet, wird auf die bestehende
Schreibweise gesetzt («tiere» wird «Tiere»). Ähnliche Werte («Tier» neben «Tiere») meldet die
Oberfläche als Hinweis, entscheidet aber nicht selbst. Automatisch erfasst: Dateiname, Grösse,
Format, Seitenzahl (PDF: Seiten; Word: Angabe aus den Dokumenteigenschaften, sonst leer; Text:
leer; Bild: 1), letzte Änderung der Datei (vom Browser mitgeschickt, sonst aus den
Dokumenteigenschaften), Upload-Datum, Lehrperson. Die Lehrperson ist bei Header-Anmeldung der
angemeldete Name, sonst ein Feld «Hochgeladen von» (im Browser gemerkt), sonst «Lehrperson».
Zusätzlich: Prüfsumme gegen doppeltes Hochladen derselben Datei, nachträgliches Bearbeiten der
Metadaten (nicht der Datei), Download der Originaldatei.

**L-02.** Im Editor öffnet «Aus der Ablage wählen» eine Tabelle mit Filtern (Suche in Name,
Beschreibung und Dateiname; Fach; Niveau; Tag; Format; Lehrperson; Upload-Zeitraum). Ganze
Lernmaterialien werden ausgewählt. Die Lektion speichert Verweise (`materialien`) und weiterhin
den zusammengesetzten Materialtext als Momentaufnahme (siehe E9). Bestehende Lektionen mit
eingebetteten Quellen bleiben unverändert lauffähig; ihre Quellen lassen sich im Editor mit
«In die Ablage übernehmen» global ablegen.

**L-03.** «Archivieren» ist das Löschen; Daten, Datei und Embeddings bleiben erhalten.
Archivieren geht nur, wenn keine nicht archivierte Lektion das Material verwendet, sonst nennt
die Meldung die Lektionen. Wird eine archivierte Lektion wiederhergestellt, deren Material
inzwischen archiviert ist, wird das Material automatisch mit wiederhergestellt (sonst wäre die
Bedingung verletzt). Archivierte Materialien sind in der Auswahl nicht wählbar.

**T-27.** SVG-Favicon plus PNG/ICO für ältere Browser, auf allen Seiten, ohne Anmeldung
erreichbar.

**T-28.** «Stoppen» erscheint in der Warteanzeige bei allem, was die lernende Person (oder eine
Lehrperson im Testlauf) als Text an den Tutor schickt: Antwort, Verständnisfrage, «Theorie
dazu», «Genauer erklären», Einwand, Einstufungsantworten. Ergänzt: Der Server verwirft ein
Ergebnis, das nach dem Stopp eintrifft, bevor es Profil oder Zählung verändert; ein Stopp zählt
nicht als Versuch. Die Nachricht steht danach wieder im Eingabefeld. Kommt der Stopp zu spät (die
Antwort war schon übernommen), erscheint sie normal. Bei Ollama wird die Generierung tatsächlich
abgebrochen, damit die nächste Anfrage nicht hinter der alten wartet.

**T-29.** «Kompatibel zum verwendeten LLM» wird so gelesen: Das Embedding-Modell läuft beim
gleichen Anbieter wie das Chat-Modell (Ollama lokal, OpenAI in der Cloud), deckt dieselben
Sprachen ab und stammt nach Möglichkeit aus derselben Modellfamilie. Mit qwen3:30b ist das
`qwen3-embedding:0.6b`. Ein Chat-Modell selbst erzeugt keine brauchbaren Embeddings. Pro Material
gespeichert: Anbieter, Modell, Dimension, Distanzmass, Chunkgrösse, Overlap, Abfragepräfix,
Anzahl Chunks, Zeitpunkt und Dauer (Katalog und Metadaten jedes Chunks), Metadaten und
Datei-Metadaten (Katalog, Chunk-Metadaten mit Material-ID, Name, Seite, Abschnitt), Speicherort
der Originaldatei, Embeddings (ChromaDB). Bilder: Text per OCR (Tesseract, falls installiert),
sonst wird das Bild abgelegt, aber nicht indexiert.

**T-30.** Auszüge werden pro Schrittart mit einer passenden Abfrage geholt (Theorie: Konzept oder
offene Lernziele; Aufgabe: zuletzt erklärte Theorie; Gegenprüfung und Bewertung: Aufgabe und
Antwort; Chat: Frage und aktuelles Konzept; Einstufung und Abschluss: Lernziele). Sie stehen im
Benutzerteil des Prompts; der Systemprompt nennt nur noch die Quellen und bleibt pro Lektion
konstant (Prompt-Cache). Jede Abfrage wird protokolliert, die Lehrperson sieht Fundstellen und
Ähnlichkeit im Lernverlauf. Theorieschritte und Antworten im Chat zeigen die Fundstelle mit Seite.
Ergänzt: Fällt die Vektordatenbank aus oder ist ein Material nicht mit dem aktuellen Modell
indexiert, arbeitet der Tutor wie bisher mit dem ganzen Material (mit Warnung).

**T-31.** Semantische Version in der Datei `VERSION`, Short-Hash zur Laufzeit aus dem
Git-Verzeichnis (ohne Git-Befehl) oder aus `ITS_GIT_COMMIT` (Docker). Anzeige als
`0.5.0+abc1234` (SemVer-Build-Metadaten) im Fuss jeder Seite, unter `/api/version` und beim
Serverstart. Historie in `CHANGELOG.md`.

## 3. Entscheide

| Nr. | Entscheid | Begründung |
|---|---|---|
| E1 | Vektordatenbank ChromaDB als eigener Dienst (`chroma run` lokal oder Container `chromadb/chroma`), Zugriff über `ITS_VEKTOR_DB_URL` | Läuft auf Windows ohne Docker mit einem `pip install`, keine Erweiterung kompilieren, kleiner Eingriff. pgvector bräuchte auf a9-mega Docker Desktop oder eine eigene PostgreSQL-Installation mit Erweiterung |
| E2 | Metadaten im bestehenden SQLite-Speicher (Tabelle `materialien`), nicht in PostgreSQL | Eine Datenbank für alle ITS-Daten statt einer dritten. Die Kombination Metadaten plus Vektoren in PostgreSQL/pgvector ist geprüft und vorbereitet: Der Katalog ist ein eigenes Modul, die Vektoren hängen an einer Schnittstelle; ein späterer Umzug betrifft beide Module, nicht den Tutor |
| E3 | Originaldateien und extrahierter Text mit `filedepot` (DEPOT) im Dateisystem, nie in einer Datenbank | Vorschlag aus dem Feedback, MIT-Lizenz, gepflegt (Version 0.12.0 vom Juli 2026), eine kleine Abhängigkeit; ein späterer Wechsel auf S3 ist eine Konfiguration |
| E4 | Embeddings über Ollama mit `qwen3-embedding:0.6b` (1024 Dimensionen, mehrsprachig), bei OpenAI `text-embedding-3-small`, Mock für Tests | Gleicher Anbieter und gleiche Modellfamilie wie qwen3:30b, klein genug für den gemeinsamen Grafikspeicher |
| E5 | RAG schaltet automatisch ab einer Materialgrösse ein (Standard 4000 Tokens), pro Lektion übersteuerbar («automatisch», «immer Auszüge», «immer ganzes Material») | Kleine Lektionen bleiben wie evaluiert, grosse passen ins Kontextfenster; die Einstellung erlaubt Experimente |
| E6 | Chunks bis 1200 Zeichen an Absatz- und Satzgrenzen, Overlap 300 Zeichen (25 %), innerhalb eines Abschnitts | Ergebnis des Experiments mit `tests/eval/eval_chunking.py` (Abschnitt 4); auf a9-mega mit qwen3-embedding zu bestätigen |
| E7 | Version 0.5.0 für diesen Auftrag; 1.0.0 ist der Stand für den Pilotbetrieb | MVP vor dem Pilot, Minor pro Auftrag, Patch für Korrekturen |
| E8 | Stopp über eine Anfrage-ID: Abbruch-Endpunkt, Prüfung vor dem Übernehmen, bei Ollama Streaming mit Abbruch | Zuverlässig auch hinter Cloudflare, wo ein abgebrochener Browser-Request den Server nicht sicher erreicht |
| E9 | Die Lektion speichert Verweise und den zusammengesetzten Text als Momentaufnahme | Lernverläufe bleiben rekonstruierbar, alle bestehenden Prüfungen (Kopie, Quellen, Fallback-Abschnitte) arbeiten unverändert |
| E10 | Die Lehrperson als Uploader: Header-Name, sonst Feld «Hochgeladen von» | Mit gemeinsamem Passwort gibt es keine Personen; ein Feld ist ehrlicher als ein erfundener Name |
