# ITS-MVP – Intelligentes Tutorielles System

Erster lauffähiger MVP gemäss Projektbeschreibung (DLH-Innovationsfonds, EB Zürich).
Umfang: Lernenden-Flow (Einstufung → adaptiver Lernpfad → KI-Feedback → Abschluss)
plus Lehrpersonen-Monitoring light. Der komplette Lernverlauf wird protokolliert.

## Was der MVP kann

- **Onboarding**: Lernende melden sich mit Pseudonym (plus Zugangscode, optional einer vierstelligen PIN) an und sehen ihre eigenen Lernsequenzen.
- **Wissenseinstufung**: 3 KI-generierte Einstiegsfragen bestimmen das Startniveau (basic / intermediate / advanced).
- **Lernendenprofil**: Niveau, Fortschritt, Trefferquote, behandelte Konzepte; wird laufend aktualisiert.
- **Adaptiver Lernpfad**: Die KI generiert Lernschritte aus dem Lektionsmaterial. Richtig → weiter. Falsch → Hinweis und zweiter Versuch, nochmals falsch → Vereinfachung, und nur wenn beide Versuche falsch waren, eine Stufe tiefer (nie direkt von «Vertieft» auf «Grundlagen»). Höher geht es nie stillschweigend: Nach drei richtigen Antworten in Folge zum gleichen Konzept fragt der Tutor, ob die lernende Person anspruchsvollere Aufgaben möchte («Ja, gerne» / «Lieber so bleiben»). Lernende können ihr Niveau jederzeit über das Bedienelement «Niveau» festlegen (Einträge «Automatisch (empfohlen)», «Grundlagen», «Fortgeschritten», «Vertieft», T-16) oder im Chat einen Wunsch äussern («Ich möchte auf dem Grundniveau bleiben»); das festgehaltene Niveau hat Vorrang. Pro Lektion lässt sich die Niveauanpassung auf «automatisch», «nur nach unten» oder «fix» stellen. Jede Adaption wird begründet und protokolliert (Transparenzprinzip aus dem Systemkonzept).
- **KI-Feedback mit dreistufiger Bewertung**: Antworten werden als korrekt, teilweise korrekt oder falsch beurteilt (Kategorien und Feedback-Regeln nach dem Vorbild des LLMTutor-Projekts von Swiss Learning Analytics). Die Bewertung läuft in zwei Schritten: Die zentralen Elemente einer vollständigen Antwort (1 bis 4) legt seit D-10 schon die Aufgabengenerierung fest und speichert sie mit der Aufgabe; die Frage nennt jeden dieser Teile, und eine Regel erkennt einteilige Fragen («Welche … ist …?», «Wer ist …?») mit mehreren Elementen. Die Bewertung prüft genau diese Elemente (korrekt, vertretbar, ungenau, nicht beurteilbar, falsch, fehlt) und bemängelt nichts, was die Frage nicht verlangt hat; das Urteil leitet der Code daraus ab. «Richtig» heisst alle Elemente korrekt, «teilweise» mindestens eines korrekt und keines falsch, «falsch» keines korrekt oder ein sachlicher Widerspruch. Die Elemente erscheinen im Lernverlauf der Lehrperson. Die Bewertungsstrenge (nachsichtig, ausgewogen, streng) ist pro Lektion einstellbar; sachliche Fehler gelten in jeder Stufe als falsch. Bei «teilweise» zeigt der Tutor Feedback mit Hinweis und lässt die lernende Person entscheiden (D-07): «Antwort ergänzen» (die bisherige Antwort steht zur Bearbeitung bereit; bewertet wird der neueste Stand, höchstens drei Ergänzungen pro Aufgabe), «Lösung ansehen» oder «Weiter zur nächsten Aufgabe». Ein so abgeschlossener Schritt gilt als bearbeitet und «teilweise», zählt weder als Fehler noch als richtig und setzt die Serie richtiger Antworten zurück (Entscheid E1).
- **Faire Bewertung (Auftrag 3, Oktober 2026)**: Jedes erwartete Element besteht aus Dimension und erwartetem Inhalt; Dimensionen werden sinngemäss ausgelegt (eine Schule kann die «verantwortliche Person» sein). Eine Nachbesserung wird als neuester Stand bewertet: Der falsche Teil eines früheren Versuchs zählt nicht mehr, ein früher korrektes Element fällt nicht auf «fehlt» zurück, und kein Hinweis wiederholt einen früheren (D-14). Eine Antwort ist nie falsch, nur weil sie von der Musterlösung abweicht oder im Material fehlt: Ist sie unter einer Annahme richtig, die der Fall offenlässt, gilt sie als «vertretbar» (zählt wie korrekt, die Rückmeldung nennt die Annahme); geht sie in einer Lektion ohne Allgemeinwissen über das Material hinaus, lautet der Status «nicht beurteilbar» (zählt wie ungenau). Nach «teilweise» oder «falsch» können Lernende einmal pro Aufgabe mit «Ich sehe das anders» und einer kurzen Begründung widersprechen; das zählt nicht als Versuch (D-15). Vorsichtige Formulierungen wie «vermutlich» sind kein Mangel, wenn der Fall den Punkt offenlässt (D-16). «Lösung ansehen» zeigt je Element, was erwartet war, was die lernende Person schrieb, den Status und die Begründung; stimmen Antwort und Lösung inhaltlich überein, korrigiert der Tutor das Urteil offen (D-17). Der Chat kennt die letzte Bewertung; widerspricht er ihr, sagt er ausdrücklich, dass er sich geirrt hat, und bietet «Antwort neu bewerten lassen» an (D-18).
- **Bewertung auf der Ebene der Frage (Auftrag 5, Oktober 2026)**: Jedes Element wird an der Tiefe gemessen, die die Frage erkennbar verlangt, nicht an der feineren Unterscheidung der Musterlösung; bei «Begründe kurz» genügt eine kurze, passende und sachlich richtige Begründung (D-19). Eine Formulierung mit derselben Bedeutung und demselben Fachbegriff gilt wie der Wortlaut im Material, bei jeder Bewertungsstrenge; stuft das Modell ein Element trotzdem als ungenau ein, obwohl die Antwort den erwarteten Schlüsselbegriff enthält, folgt ein Korrekturhinweis (D-20). Feedback und Hinweis nennen keinen Schlüsselbegriff und keinen erwarteten Inhalt eines noch nicht erfüllten Elements, den die lernende Person nicht selbst geschrieben hat; bleibt ein solcher Verstoss nach dem Korrekturversuch bestehen, wird der Hinweis ersetzt und der Feedbacktext um die betroffenen Sätze gekürzt. Multiple Choice ist ausgenommen (D-21).
- **Stimmige Aufgaben (D-13)**: Theorie und Aufgabe nennen die Merkmale, an denen man ein Konzept im Fall erkennt; ein Fall ohne diese Merkmale wird neu erzeugt, und der Titel verrät die Lösung nicht. Eine Gegenprüfung löst jede neue Aufgabe ohne Kenntnis der Musterlösung (im Vorabruf, abschaltbar mit `ITS_MUSTERLOESUNG_PRUEFEN`). Weicht sie ab, wird die Aufgabe einmal neu erzeugt; weicht sie erneut ab, gilt die Musterlösung als unsicher und die abweichende Lösung als vertretbare Alternative. Die Lehrperson sieht das Ergebnis im Lernverlauf.
- **Sicherheitsfrage (metakognitiv)**: Vor der ersten Bewertung jeder Aufgabe geben Lernende an, wie sicher sie sich sind (1-10). Liegt die Einschätzung deutlich daneben (ab 8 und falsch, bis 3 und richtig), ergänzt der Tutor einen kurzen Satz dazu; sonst nicht, damit es nicht zur Routine wird. Die Abschlusszusammenfassung zeigt die durchschnittliche Sicherheit bei richtigen und bei nicht richtigen Antworten mit einem Hinweis für das weitere Lernen, die Lehrperson sieht diese Kalibrierung pro Sequenz.
- **Fragequalität (Eigenleistung statt Abschreiben)**: Jede bewertete Aufgabe verlangt eine eigene Denkleistung (anwenden auf einen neuen Fall, begründen, vergleichen, vorhersagen, Fehler finden, mit eigenen Worten an einem neuen Beispiel erklären), passend zum Niveau. Der Tutor liefert zu jeder Aufgabe intern eine Musterlösung und Schlüsselbegriffe, die Lernende nie sehen. Nach der Generierung prüft der Code deterministisch, ob ein Lösungsbegriff oder sein Wortstamm in der Frage steht, ob das Beispiel der letzten Theorie wiederverwendet wird oder ob die Antwort direkt aus dem eben gezeigten Text abschreibbar ist; bei einem Treffer wird einmal neu generiert und der Verstoss protokolliert. Die Regeln stehen gebündelt im Regelkatalog `app/didaktik.py`.
- **Einsatzart pro Lektion**: «Einführung» (Standard) setzt kein Vorwissen voraus. Bewertete Aufgaben beziehen sich nur auf Konzepte, die in der Sequenz schon erklärt wurden; verlangt eine Aufgabe trotzdem ein neues Konzept, kommt zuerst ein Theorieschritt dazu, auch auf höherem Niveau. Die Einstufung fragt dann nach Alltagswissen statt nach Fachbegriffen. «Vertiefung» darf Konzepte aus dem Material voraussetzen; eine falsche Antwort zu einem noch nicht erklärten Konzept führt zu einer Erklärung und nicht zu einer Niveausenkung.
- **Erklärtiefe bei Nachfragen**: «Theorie dazu» bringt einen neuen Zugang statt denselben Text, «Genauer erklären» erklärt das Warum und Wie. Wiederholtes Nachfragen zum gleichen Konzept folgt einer im Code festgelegten Eskalation: zuerst ein anderes Beispiel, dann eine Analogie oder Schritt-für-Schritt-Erklärung, dann die ehrliche Aussage, dass das Material ausgeschöpft ist, mit einem Angebot. Bereits gezeigte Texte gehen mit, eine Ähnlichkeitsprüfung verhindert Wiederholungen, eine Tonprüfung defensive Einstiege wie «Im Material wird nicht erwähnt, dass …». Ist Allgemeinwissen erlaubt (Standard), kann der Tutor darüber hinaus erklären; solche Ergänzungen sind farbig markiert und als «ausserhalb des Lektionsmaterials» beschriftet. Bewertet wird anhand des Materials und des Sachverhalts; eine Antwort, die darüber hinausgeht, prüft der Tutor mit gesichertem Allgemeinwissen, sofern die Lektion es erlaubt (D-15).
- **Theorie-Schritte**: Der Lernpfad besteht aus Input- und Anwendungs-Schritten. Der Tutor erklärt neue Konzepte zuerst (mit Beispiel), bevor Aufgaben dazu kommen – wie viel Theorie, entscheidet er adaptiv: Auf Niveau basic gibt es Input vor jedem neuen Konzept, auf intermediate zum Einstieg, auf advanced nur nach Fehlern. Nach zwei Fehlversuchen wird das Konzept neu und einfacher erklärt. Theorie-Schritte werden nicht bewertet und zählen nicht in die Quote. Lernende können zudem jederzeit selbst Theorie anfordern («Theorie dazu», «Genauer erklären»).
- **Mathematische Formeln**: Der Tutor schreibt Formeln in LaTeX, das UI rendert sie mit KaTeX sauber als Brüche, Exponenten, Wurzeln usw. – im Lern-Chat, in der Einstufung und im Lernverlauf der Lehrperson. Hinweis: KaTeX wird von einem CDN geladen; für den Betrieb ganz ohne Internet müsste es lokal ins Projekt gelegt werden.
- **Chat-Dialog**: Das Lernen läuft als Dialog. Der Tutor liefert Input und Aufgaben als Chat-Nachrichten, und Lernende können ihm jederzeit Verständnisfragen stellen («Frage stellen»), ohne dass dies bewertet wird. Der Tutor antwortet materialgebunden und verrät die Lösung der aktuellen Aufgabe nicht, sondern gibt Denkanstösse. Auch diese Fragen erscheinen im Lernverlauf der Lehrperson. Solange der Tutor arbeitet, zeigt der Chat eine Warteanzeige («Dein Tutor denkt nach …», nach 20 Sekunden mit beruhigendem Hinweis) und alle Aktionsbuttons sind deaktiviert; das Eingabefeld bleibt beschreibbar, nichts wird doppelt abgeschickt.
- **Abschluss**: Zusammenfassung mit Lernzielabgleich, Empfehlung und Kalibrierung der Selbsteinschätzung.
- **Quellenverweise**: Ist das Material nach Quellen gegliedert (`### Quelle: <Dateiname>`, wie es der Editor erzeugt), steht unter jedem Theorieschritt eine kleine Quellenzeile. Der Code prüft die Angabe des Tutors gegen die Lektion; eine erfundene Quelle wird nie angezeigt, die Lehrperson sieht sie im Lernverlauf als verworfen.
- **Wissensstufen**: Pro Lektion legt die Lehrperson fest, ob der Tutor neben dem Material auch Allgemeinwissen (Standard) und eine Internetrecherche verwenden darf. Die Recherche ist zusätzlich auf dem Server über `ITS_WEB_SEARCH` abschaltbar und standardmässig aus; sie läuft über einen selbst betriebenen SearXNG-Dienst. An den Suchdienst gehen nur Konzept und Lektionstitel, nie Name, Antworten oder Chattext. Ergebnisse erscheinen farbig markiert mit den Quellen als Links und dem Hinweis, dass sie nicht von der Lehrperson geprüft sind. Bewertet wird immer nur anhand des Materials. Einrichtung in `docs/INTERNETRECHERCHE.md`.
- **Eigener Lernverlauf**: Lernende öffnen in ihrer Übersicht den Verlauf eigener pausierter, abgeschlossener, abgebrochener und (eingeblendet) archivierter Sequenzen: Aufgaben, eigene Antworten, Bewertungen und Feedback, oben die Konzepte mit falschen oder teilweise richtigen Antworten mit Sprung zur Stelle. Interne Angaben wie Adaptionsbegründungen, Antwortzeiten, Fallbacks oder Musterlösungen bleiben der Lehrperson vorbehalten.
- **Lernsequenzen pro Person**: Eine Lernsequenz gehört einer Person (Benutzername, Gross-/Kleinschreibung egal) und einer Lektion. Nach der Anmeldung zeigt die Startseite die eigenen Sequenzen mit Lektion, Fortschritt, Niveau, Status und letzter Aktivität, jeweils mit «Fortsetzen» und «Neu beginnen». Fortsetzen klappt auch auf einem anderen Gerät an genau derselben Stelle; der ganze bisherige Dialog mit den eigenen Antworten steht wieder im Chat, eine Trennlinie markiert Pause und Fortsetzung (T-14). Pro Person und Lektion gibt es höchstens eine offene Sequenz; «Neu beginnen» archiviert die bisherige nach einer Bestätigung. Status: aktiv, pausiert, abgeschlossen, abgebrochen, archiviert; jeder Wechsel landet im Event-Log. Wer beim ersten Start eine PIN setzt, schützt den Namen vor fremdem Weiterlernen. In der Lernansicht gibt es oben «Pausieren und später weiterfahren» und «Lektion abbrechen» (mit Bestätigung); eine abgebrochene Sequenz bleibt für die Lehrperson mit Zeitpunkt sichtbar.
- **Lehrpersonen-Sicht** (`/teacher`): Links eine Seitenleiste mit Lernenden und ihren Sequenzen (neueste zuoberst, mit Startdatum und -zeit, die letzte Aktivität als Tooltip, T-26), filterbar nach Name, Lektion, Status und Testläufen von Lehrpersonen (die Filter wirken sofort). Ein Klick zeigt den vollständigen Lernverlauf als Zeitleiste in der Mitte, ohne Seitenwechsel. Sequenzen lassen sich einzeln oder gemeinsam archivieren und wiederherstellen; archivierte sind standardmässig ausgeblendet und über den Statusfilter sichtbar (T-20). Angemeldete Lernende erhalten auf Lehrpersonen-Endpunkten 403. Die Antwortzeiten des Sprachmodells liegen in einem eigenen Bereich. Auf schmalen Bildschirmen klappt die Seitenleiste ein.
- **Lektionen verwalten** (`/teacher/lessons`): Liste aller Lektionen mit Anzahl Lernziele und Quellen, letzter Änderung und Anzahl Sequenzen. «Ansehen» zeigt Lernziele, Quellen, Material, Hinweise und Tutor-Einstellungen. «Bearbeiten» öffnet den Editor mit allen Werten inklusive Quellenliste; beim Speichern werden Version und Änderungsdatum nachgeführt, laufende Sequenzen arbeiten ab dem nächsten Schritt mit dem neuen Material. «Archivieren» (früher «Löschen») nimmt die Lektion aus der Auswahl, Lernverläufe bleiben lesbar; «Wiederherstellen» holt sie zurück, «Duplizieren» legt eine Kopie an (T-17, T-20). Eine archivierte Lektion lässt sich nicht bearbeiten: Der Editor zeigt statt des Formulars einen Hinweis mit Link zur Lektionsliste, auch beim direkten Aufruf der Adresse, und die Details eines Lernmaterials verlinken archivierte Lektionen nicht in den Editor (L-04).
- **Teaching Mode** (N-06, Auftrag 5): «Im Teaching Mode testen» startet bei einer nicht archivierten Lektion einen Testlauf, in dem unter jedem Schritt des Tutors «Teach the Tutor» steht. Die Lehrperson schreibt eine Anweisung und wählt, ob sie nur für das Thema des Schritts gilt (gebunden an dessen Konzept, wirkt im Benutzerteil aller Anfragen zu diesem Konzept) oder für die ganze Lektion: Dann schlägt der Tutor eine verallgemeinerte Fassung vor, die Lehrperson ändert und bestätigt sie, und sie steht im Systemprompt (scheitert der Vorschlag, bleibt der eigene Text). Gespeicherte Anweisungen liegen in der Lektion unter `tutor_anweisungen`, getrennt von den Hinweisen ans Tutorverhalten, erhöhen die Version und wirken ab dem nächsten Aufruf des Tutors, auch in laufenden Sequenzen. Der Editor listet sie mit Geltung, Konzept und Datum und löscht einzelne; der Lernverlauf der Teaching-Sequenz zeigt jede Anweisung. Normale Testläufe und Sequenzen von Lernenden zeigen nichts davon.
- **Tutor-Einstellungen pro Lektion** (Editor, Abschnitt 4; im JSON unter `einstellungen`, fehlende Werte = Standard): Einsatzart (Einführung/Vertiefung), Niveauanpassung (automatisch/nur nach unten/fix), Bewertungsstrenge (nachsichtig/ausgewogen/streng), Materialzugriff (automatisch/immer Auszüge/immer ganz, T-30), Wissensquellen (Material, optional gekennzeichnetes Allgemeinwissen).
- **Material prüfen** (Editor, Abschnitt 5): Die KI gleicht das Material mit den Lernzielen ab und zeigt pro Lernziel, ob Erklärung, Beispiel und Begründung vorhanden sind, dazu einen Hinweis bei sehr kurzem Material. Das ist eine Empfehlung und verhindert das Speichern nicht.
- **Lernmaterialien global ablegen** (`/teacher/materialien`, L-01, Auftrag 4): Jede hochgeladene Datei (PDF, Word, Text, Markdown, Bilder) wird ein Lernmaterial, das alle Lektionen verwenden können. Beim Hochladen ergänzt die Lehrperson Name, mögliche Fächer, Niveau (Schätzung), Beschreibung (höchstens 128 Zeichen) und Tags; bestehende Werte erscheinen als Vorschläge, eine abweichende Schreibweise («tiere») übernimmt die bestehende («Tiere»), ähnliche Werte («Tier» neben «Tiere») meldet die Oberfläche. Automatisch erfasst werden Dateiname, Grösse, Format, Seitenzahl, letzte Änderung der Datei, Upload-Datum und Lehrperson (bei Header-Anmeldung der angemeldete Name, sonst das Feld «Hochgeladen von»). Die Originaldatei und der seitenweise extrahierte Text liegen mit filedepot im Dateisystem (`ITS_MATERIAL_DIR`), nie in der Datenbank; der Katalog steht in der SQLite-Tabelle `materialien`. Dieselbe Datei wird erkannt. Bilder werden per OCR gelesen, wenn Tesseract installiert ist. Die Seite zeigt alle Materialien mit Filtern, Details mit Textvorschau, Download und nachträglich änderbaren Metadaten.
- **Lernmaterialien in Lektionen wählen** (L-02): Im Lektionseditor öffnet «Aus der Ablage wählen» eine Tabelle mit Filtern nach Metadaten und Datei-Metadaten (Suche, Fach, Niveau, Tag, Format, Lehrperson, Upload-Zeitraum); gewählt werden ganze Lernmaterialien. Neue Dateien gehen über denselben Dialog in die Ablage. Die Lektion speichert Verweise (`materialien`) und den zusammengesetzten Text als Momentaufnahme; ältere, lektionsinterne Quellen bleiben und lassen sich mit «In die Ablage übernehmen» global ablegen.
- **Lernmaterialien archivieren** (L-03): «Archivieren» entspricht dem Löschen und geht nur, wenn keine aktive Lektion das Material verwendet (die Meldung nennt sie). Datei, Text und Embeddings bleiben erhalten, «Wiederherstellen» holt das Material zurück. Wird eine Lektion wiederhergestellt, deren Material inzwischen archiviert ist, kommt das Material mit.
- **Vektordatenbank und RAG** (T-29, T-30): Ist `ITS_VEKTOR_DB_URL` gesetzt, zerlegt der Server jedes Lernmaterial nach dem Upload im Hintergrund in Chunks (bis 1200 Zeichen an Absatz- und Satzgrenzen, Overlap 300 Zeichen innerhalb eines Abschnitts, Seite und Abschnitt pro Chunk), bettet sie beim Anbieter des Chat-Modells ein (Ollama: `qwen3-embedding:0.6b`) und legt sie in ChromaDB ab, einem eigenen Dienst. Pro Material sind Modell, Parameter, Anzahl Chunks und Zeitpunkt gespeichert; ein Modellwechsel erscheint als «anderes Modell» mit «Neu indexieren». Ist das Material einer Lektion gross (Standard ab 4000 Tokens) oder steht die Einstellung «Materialzugriff» auf «Immer Auszüge», bekommt der Tutor pro Schritt nur die passenden Auszüge: Theorie und Einstufung suchen nach den Lernzielen oder dem Konzept, Aufgaben nach der vorangehenden Theorie, die Bewertung nach Aufgabe und Antwort, der Chat nach der Frage. Der Systemprompt nennt dann nur die Quellen und bleibt pro Lektion gleich. Unter Theorieschritten und Chat-Antworten steht die Fundstelle mit Seite («OR Haftpflicht, S. 3, Art. 56»), im Lernverlauf sieht die Lehrperson jede Abfrage mit Treffern und Ähnlichkeit. Ohne Vektordatenbank oder bei einem Ausfall arbeitet der Tutor wie bisher mit dem ganzen Material.
- **Bearbeitung stoppen** (T-28): Solange der Tutor an einer Antwort, Verständnisfrage, Erklärung, einem Einwand oder der Einstufung arbeitet, zeigt die Warteanzeige «Stoppen». Der Server bricht die Generierung ab (bei Ollama wirklich, damit die nächste Anfrage nicht wartet) und verwirft ein nachträglich eintreffendes Ergebnis; gestoppt zählt nicht als Versuch. Die Nachricht steht danach wieder im Eingabefeld. Im Lernverlauf der Lehrperson steht «Bearbeitung gestoppt».
- **Version und Favicon** (T-31, T-27): Der Fuss jeder Seite zeigt die semantische Version und den Commit (`0.6.0+abc1234`), ebenso `/api/version` und das Log beim Start. Regeln zum Hochzählen in `CHANGELOG.md` und `app/version.py`. Alle Seiten haben ein Favicon.
- **Lektionen erstellen** (`/teacher/lessons/new`): Lehrpersonen erstellen Lektionen direkt im Browser. Material als Text einfügen oder als Datei hochladen (PDF, Word, Text/Markdown), den Titel selbst festlegen (Pflichtfeld) und auf dieser Grundlage Lernziele von der KI vorschlagen lassen (als «experimentell» gekennzeichnet, T-18), optional Hinweise ans Tutorverhalten («Arbeite mit Alltagsbeispielen», «Sei streng bei Fachbegriffen»). Nach dem Speichern erscheint die Lektion in der Auswahl auf der Lernenden-Startseite.
- **Rollen und Zugangsschutz**: Es gibt die Rollen «lernend» und «lehrperson», durchgesetzt auf dem Server. Alle Seiten unter `/teacher` und alle Endpunkte unter `/api/teacher` hängen an einer zentralen Rollenprüfung (`app/auth.py`); ohne Login gibt es 401 bzw. eine Weiterleitung auf `/teacher/login`. Lernende sehen keine Elemente für Lehrpersonen. Lehrpersonen melden sich mit `TEACHER_PASSWORD` an, Lernende mit Pseudonym plus Zugangscode (`CLASS_CODE`). In der Kopfzeile aller Seiten, auch in der laufenden Lernansicht, steht «Abmelden» (T-22): Es löscht die Cookies und die ITS-Einträge im localStorage, pausiert eine laufende Sequenz und führt zur leeren Anmeldemaske bzw. Login-Seite; das wirkt auch ohne `TEACHER_PASSWORD`. Beides lässt sich für die lokale Entwicklung deaktivieren, indem die Variablen leer bleiben. Optional übernimmt das ITS Name und Rolle aus Headern eines Proxys wie Cloudflare Access (`ITS_TRUST_PROXY_HEADERS`, siehe `docs/DEPLOYMENT-CLOUDFLARE.md`). Lernsequenzen, die eine Lehrperson startet, sind Testläufe und erscheinen im Monitoring nur mit dem Filter «Testläufe von Lehrpersonen anzeigen» (T-21).
- **Deployment-Paket**: Dockerfile und docker-compose mit Caddy-Reverse-Proxy – HTTPS inklusive automatischem Let's-Encrypt-Zertifikat. Schritt-für-Schritt-Anleitung für einen VPS in `docs/DEPLOYMENT.md`; Alternative ohne eigenen Server: lokaler Betrieb mit Cloudflare Tunnel, siehe `docs/DEPLOYMENT-CLOUDFLARE.md`.
- **LLM-Abstraktion**: Provider per `.env` umschaltbar – Cloud (Anthropic, OpenAI-kompatibel) oder lokal (Ollama). `mock` läuft ganz ohne LLM für Demos und Tests.

## Schnellstart

```bash
cd its-mvp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Provider und Keys eintragen
uvicorn app.main:app --reload
```

Dann im Browser:
- Lernende: http://localhost:8000/
- Lehrperson: http://localhost:8000/teacher

Auf Windows genügen `setup.bat` (einmalig) und `start.bat`. Letzteres startet
den Server auf Port **8010**, damit Port 8000 für andere lokale Anwendungen
frei bleibt (siehe `docs/DEPLOYMENT-CLOUDFLARE.md`).

**Wichtig:** Ohne Anpassung der `.env` läuft der Mock-Provider – ohne KI. Er
bewertet nur heuristisch (sehr kurze Antworten gelten als falsch) und liefert
feste Beispieltexte. Echte fachliche Bewertung, echte Aufgaben und echtes
Tutoring gibt es erst mit einem konfigurierten LLM:

```ini
# Cloud (schnellster Weg)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# oder lokal auf RIB-AI-01 (On-Premise, datenschutzkonform)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

## Architektur

```
Browser (static/*.html, materialien.js, version.js)
   │  REST/JSON
FastAPI (app/main.py)
   ├─ tutor.py        ITS-Kernlogik: Einstufung, Profil, Adaption, Prompts
   ├─ rag.py          RAG: Modus, Retrieval pro Schrittart, Auszüge, Fundstellen (T-30)
   ├─ llm.py          Provider-Abstraktion: anthropic | openai | ollama | mock
   ├─ abbruch.py      Stoppbare Anfragen (T-28)
   ├─ materialien.py  Ablage: Katalog in SQLite, Dateien mit filedepot (L-01)
   ├─ vektoren.py     Chunking, Embeddings, ChromaDB (T-29)  ──►  ChromaDB (eigener Dienst)
   ├─ store.py        SQLite: Sessions + vollständiges Event-Log
   ├─ version.py      Version und Commit (T-31)
   └─ lessons/        Lektionen als JSON (materialgebunden, austauschbar)
```

Designentscheide, angelehnt ans Systemkonzept vom April 2026:

- **Lektion als zentrale Einheit**: Eine Lektion ist eine JSON-Datei mit Titel, Lernzielen, Material und Fallback-Einstufungsfragen. Neue Lektion = neue Datei in `app/lessons/`, kein Codeeingriff.
- **Materialgebunden**: Der Systemprompt verpflichtet den Tutor auf das Lektionsmaterial und macht Unsicherheit sichtbar (Verlässlichkeit vor Eloquenz).
- **Trennung Inhalt/Tutorlogik**: Die Adaptionslogik (tutor.adapt) ist deterministischer Code, kein LLM-Entscheid – nachvollziehbar und testbar. Das LLM generiert Inhalte, Bewertungen und Feedback.
- **Lernpfade rekonstruierbar**: Jedes Ereignis (Fragen, Antworten, Bewertungen, Adaptionen mit Begründung) landet im Event-Log und ist in der Lehrpersonen-Sicht einsehbar.
- **Robustheit**: Scheitert ein LLM-Aufruf oder ist die Antwort kein lesbares JSON, wird er einmal automatisch wiederholt. Erst danach greift ein Fallback: Der Tutor sagt offen, dass ihm gerade keine gute Aufgabe bzw. Erklärung gelungen ist, und bietet eine Wahl an (T-12): «Nochmals versuchen», «Abschnitt in eigenen Worten zusammenfassen» bzw. «Abschnitt aus dem Material lesen» (nur wenn sich ein passender Abschnitt bestimmen lässt), «Zum nächsten Thema» bzw. «Direkt zur Aufgabe» und «Witz zum Thema» (eigener kurzer Aufruf ohne Lektionsmaterial, sonst ein Witz aus einer festen Liste). Jede Wahl landet im Lernverlauf. Jeder Fallback erzeugt ein Event `fallback_used` mit Grund und erscheint in der Messübersicht. Seit T-09 unterscheidet der Grund leere Antworten, unlesbares JSON, falsche Struktur und technische Fehler und enthält bei Ollama done_reason, Tokenzahlen und Dauer; nach einer leeren Antwort ist der zweite Versuch verändert (ohne format=json, mit ausdrücklicher Bitte um direkte Antwort). `tests/eval/diagnose_ollama.py` prüft das Verhalten des echten Modells.

## API-Überblick

| Endpoint | Zweck |
|---|---|
| `POST /api/session/start` | Lernsequenz anlegen, Einstufungsfragen erhalten; 409, wenn zur Lektion schon eine offene Sequenz existiert (`neu_beginnen: true` archiviert sie); `teaching: true` startet den Teaching Mode (nur Lehrpersonen, sonst 403, N-06) |
| `POST /api/session/{id}/anweisung/vorschlag` | Teaching Mode: verallgemeinerte Fassung einer Anweisung (`text`, `konzept`, `schrittart`, `schritt_text`); Antwort `vorschlag` und `fallback` (N-06) |
| `POST /api/session/{id}/anweisung` | Teaching Mode: Anweisung speichern (`text`, `geltung` `thema` oder `lektion`, `konzept`, `schrittart`, `original`); erhöht die Version der Lektion (N-06) |
| `POST /api/session/{id}/assess` | Einstufung bewerten, Startniveau setzen |
| `POST /api/session/{id}/next` | Nächste Aufgabe (optional `?adaptation=simplify\|advance`); mit `?prefetch=true` nur vorbereiten, ohne Profil und Verlauf zu ändern |
| `POST /api/session/{id}/answer` | Antwort bewerten, Feedback + Adaption |
| `POST /api/session/{id}/wahl` | Wahl in einem offenen Wartezustand (`wahl`): nach gescheiterter Bewertung (T-11), nach einem Fallback (T-12), nach teilweise richtiger Antwort (D-07); dazu `widerspruch` mit Begründung in `text` (D-15) und `neu_bewerten` nach einer Selbstkorrektur im Chat (D-18). `GET …/state` liefert die offenen Möglichkeiten unter `wahl` und die zusätzlichen unter `zusatz` |
| `POST /api/session/{id}/chat` | Frage an den Tutor (unbewertet); `art`: `frage`, `theorie`, `genauer`, `allgemeinwissen`, `internet` |
| `POST /api/session/{id}/niveau` | Niveau steuern: `hoeher_ja`, `hoeher_nein`, `festhalten` (mit `level`), `automatisch` |
| `GET /api/lessons` | Verfügbare Lektionen (für die Auswahl beim Start) |
| `POST /api/teacher/lessons` | Neue Lektion anlegen |
| `GET /api/teacher/lessons` | Lektionen für die Verwaltung (`?archivierte=true` inkl. archivierter), mit geschätzter Grösse (`kontext`) |
| `POST /api/teacher/lessons/{id}/wiederherstellen` | Archivierte Lektion wiederherstellen (T-20) |
| `GET /api/teacher/lessons/{id}` | Lektion vollständig mit gültigen Einstellungen |
| `PUT /api/teacher/lessons/{id}` | Lektion ändern (Version und Änderungsdatum werden nachgeführt) |
| `DELETE /api/teacher/lessons/{id}` | Lektion archivieren |
| `POST /api/teacher/lessons/{id}/duplizieren` | Kopie «<Titel> (Kopie)» mit allen Inhalten, ohne Sequenzen, Version 1 (T-17) |
| `DELETE /api/teacher/lessons/{id}/anweisungen/{aid}` | Anweisung aus dem Teaching Mode löschen, erhöht die Version (N-06) |
| `POST /api/teacher/lessons/extract` | Text aus PDF/Word/Text-Datei extrahieren (ohne Ablage) |
| `GET /api/teacher/materialien` | Lernmaterialien der Ablage mit Filtern `q`, `fach`, `niveau`, `tag`, `format`, `lehrperson`, `von`, `bis`, `archivierte` (L-01/L-02) |
| `GET /api/teacher/materialien/werte` | Bestehende Fächer, Niveaus, Tags, Formate und Lehrpersonen (Vorschläge) |
| `POST /api/teacher/materialien` | Datei mit Metadaten hochladen (multipart: `file`, `name`, `faecher`, `niveau`, `beschreibung`, `tags`, `hochgeladen_von`, `datei_geaendert_am`, `trotzdem`); 409 bei gleicher Datei |
| `GET/PUT /api/teacher/materialien/{id}` | Details mit verwendenden Lektionen, Metadaten ändern |
| `GET /api/teacher/materialien/{id}/datei` | Originaldatei herunterladen |
| `GET /api/teacher/materialien/{id}/text` | Extrahierter Text, seitenweise (Vorschau) |
| `POST /api/teacher/materialien/{id}/archivieren` | Archivieren (= Löschen), 409 solange eine aktive Lektion es verwendet (L-03) |
| `POST /api/teacher/materialien/{id}/wiederherstellen` | Archiviertes Material wiederherstellen |
| `POST /api/teacher/materialien/{id}/indexieren` | Material neu in die Vektordatenbank legen (T-29) |
| `POST /api/teacher/materialien/indexieren` | Offene, fehlerhafte und mit anderem Modell indexierte Materialien neu indexieren (`?alle=true`: alle) |
| `GET /api/teacher/vektordb` | Vektordatenbank: eingerichtet, erreichbar, Modell, Chunk-Parameter |
| `POST /api/session/{id}/stopp` | Laufende Anfrage stoppen (`anfrage_id` aus dem Header `X-ITS-Anfrage`): `abgebrochen`, `zu_spaet` oder `unbekannt` (T-28) |
| `GET /api/version` | Version und Commit, ohne Anmeldung (T-31) |
| `POST /api/teacher/lessons/suggest-goals` | KI-Vorschlag für Lernziele (experimentell), verlangt `titel` und `material`; kein Titelvorschlag mehr (T-18) |
| `POST /api/teacher/lessons/check-material` | Material mit den Lernzielen abgleichen (Erklärung, Beispiel, Begründung) |
| `GET /api/session/{id}/state` | Zustand inkl. `wartet_auf` (Basis für das Fortsetzen) |
| `POST /api/session/{id}/fortsetzen` | Sequenz fortsetzen, liefert den Stand zum Anzeigen und unter `verlauf` den ganzen bisherigen Dialog (T-14, ohne LLM-Aufruf) |
| `POST /api/session/{id}/pausieren` | «Pausieren und später weiterfahren» |
| `POST /api/session/{id}/abbrechen` | «Lektion abbrechen» (danach nur noch neu beginnen) |
| `GET /api/me/sequenzen` | Eigene Lernsequenzen (`?archivierte=true` inkl. archivierter) |
| `GET /api/me/sequenzen/{id}/verlauf` | Eigener Lernverlauf einer nicht mehr laufenden Sequenz, nur für die eigene Person |
| `GET /api/me` | Angemeldete Identität und Rolle (für die rollenabhängige Oberfläche) |
| `POST /api/learner/login` | Anmeldung Lernende mit Name, Zugangscode und optionaler PIN |
| `GET /logout` | Abmelden für alle Rollen (T-22): löscht alle Cookies des ITS, pausiert eine laufende Sequenz und leitet auf `/teacher/login` (`?ziel=lehrperson`) bzw. `/` weiter; bei Header-Anmeldung auf die Abmeldeadresse des Proxys (T-23) |
| `POST /api/learner/logout` | Abmelden bzw. Person wechseln (dieselbe Logik, Antwort als JSON) |
| `GET /teacher/logout` | wie `/logout?ziel=lehrperson` |
| `POST /api/teacher/login` | Anmeldung Lehrperson mit Passwort |
| `GET /api/teacher/sessions` | Monitoring-Übersicht (`?testlaeufe=true` zeigt Testläufe) |
| `GET /api/teacher/sessions/{id}` | Vollständiger Lernverlauf |
| `POST /api/teacher/sessions/archivieren` | Eine oder mehrere Sequenzen archivieren (`ids`), T-20 |
| `POST /api/teacher/sessions/{id}/wiederherstellen` | Archivierte Sequenz wiederherstellen; 409, wenn die Person zur Lektion schon eine offene Sequenz hat (`?bestehende_archivieren=true` archiviert diese) |
| `GET /api/teacher/timings` | Antwortzeiten, Fehler und Fallbacks der letzten LLM-Aufrufe |
| `GET /api/teacher/websuche` | Ist die Internetrecherche auf dem Server eingeschaltet? |
| `GET /api/llm-test` | Verbindungstest zum Sprachmodell (nur Lehrpersonen) |
| `GET /api/info` | Aktiver Provider, verfügbare Lektionen |

## Konfiguration (.env)

| Variable | Bedeutung |
|---|---|
| `LLM_PROVIDER` | `anthropic`, `openai`, `ollama` oder `mock` |
| `ITS_TOTAL_STEPS` | Anzahl Lernschritte pro Durchlauf (Standard 8) |
| `ITS_DB_PATH` | Optionaler Pfad zur SQLite-DB |
| `OLLAMA_NUM_CTX` | Kontextfenster für Ollama (Standard 16384). Seit T-08 prüft der Server vor jedem Aufruf, ob der Prompt hineinpasst, und warnt im Log; der Lektionseditor warnt ab 80 Prozent |
| `ITS_ZEICHEN_PRO_TOKEN` | Faktor für die Schätzung der Promptlänge (Standard `3.4`, am 12.10.2026 mit qwen3:30b kalibriert, leicht vorsichtig) |
| `OLLAMA_KEEP_ALIVE` | Wie lange das Modell geladen bleibt (Standard 30m) |
| `OLLAMA_NUM_PREDICT` | Obergrenze für die Antwortlänge in Token (Standard 1024) |
| `OLLAMA_THINK` | Denkmodus von Reasoning-Modellen (`false` = schnell, Standard) |
| `ITS_BEWERTUNG_TEMPERATUR` | Temperatur der Antwortbewertung und der Gegenprüfung (Standard `0`, damit dieselbe Antwort gleich bewertet wird) |
| `ITS_MUSTERLOESUNG_PRUEFEN` | Gegenprüfung der Musterlösung jeder neuen Aufgabe (D-13, Standard `true`) |
| `ITS_MOCK_GEGENPRUEFUNG` | Nur für Tests: `abweichend` lässt die Gegenprüfung des Mock-Providers abweichen |
| `ITS_WEB_SEARCH` | Internetrecherche als dritte Wissensstufe (`false` = aus, Standard). Wirkt nur in Lektionen, die sie freigeben |
| `ITS_SEARXNG_URL` | Adresse eines SearXNG-Dienstes mit JSON-Ausgabe, z.B. `http://localhost:8888` |
| `LLM_TIMEOUT` | Zeitlimit pro LLM-Aufruf in Sekunden (Standard 300) |
| `OLLAMA_FORMAT_JSON` | Ollama erzwingt gültiges JSON, wo der Tutor JSON erwartet (Standard `true`) |
| `ITS_MOCK_DELAY` | Nur für Tests: Verzögerung des Mock-Providers in Sekunden |
| `ITS_MOCK_FAIL` | Nur für Tests: Schrittarten, bei denen der Mock scheitert, z.B. `THEORIE_SCHRITT`. Mit `:leer` liefert er eine leere Antwort, mit `:leer_json` nur bis zum veränderten zweiten Versuch (T-09) |
| `ITS_LESSONS_DIR` | Optionaler Pfad zum Lektionenordner |
| `TEACHER_PASSWORD` | Passwort für `/teacher`; leer = kein Login (nur lokal) |
| `CLASS_CODE` | Zugangscode für Lernende; leer = kein Code |
| `ITS_TRUST_PROXY_HEADERS` | Name und Rolle aus Proxy-Headern übernehmen (Standard `false`) |
| `ITS_USER_HEADER` | Header mit dem Benutzernamen (Standard `X-Forwarded-User`) |
| `ITS_ROLES_HEADER` | Header mit den Rollen (Standard `X-User-Roles`) |
| `ITS_TEACHER_ROLE` | Rollenname für Lehrpersonen (Standard `teacher`) |
| `ITS_LOGOUT_HEADER` | Header mit der Abmeldeadresse des Proxys bei Header-Anmeldung (Standard `X-Logout-Url`, T-23) |
| `ITS_LOGOUT_URL` | Feste Rückfalladresse zum Abmelden bei Header-Anmeldung, z.B. `/cdn-cgi/access/logout` (Standard leer; ohne Adresse kein Abmelde-Button) |
| `ITS_DOMAIN` | Domain für den HTTPS-Betrieb mit Docker/Caddy |
| `ITS_LOG_LEVEL` | Log-Stufe für alle Module: `DEBUG`, `INFO` (Standard), `WARNING`, `ERROR` (T-24) |
| `ITS_LOG_LEVELS` | Stufen einzelner Module, kommagetrennt, z.B. `its.auth=DEBUG` schreibt bei Header-Anmeldung alle ankommenden Header ins Log (T-24) |
| `ITS_MATERIAL_DIR` | Ablage der Lernmaterialien (Originale und extrahierter Text, filedepot), Standard `materialien/` im Projektordner (L-01) |
| `ITS_MATERIAL_MAX_MB` | Grösste Datei in MB (Standard 50) |
| `ITS_TESSERACT`, `ITS_TESSERACT_SPRACHEN` | Programm und Sprachen für die Texterkennung in Bildern (Standard `tesseract`, `deu+eng`) |
| `ITS_VEKTOR_DB_URL` | Adresse der ChromaDB, z.B. `http://localhost:8011`; leer = keine Vektordatenbank, kein RAG (T-29) |
| `ITS_EMBED_PROVIDER` | Anbieter der Embeddings: `auto` (wie `LLM_PROVIDER`; bei Anthropic gibt es keine), `ollama`, `openai`, `mock`, `aus` |
| `ITS_EMBED_MODEL` | Embedding-Modell (Standard Ollama `qwen3-embedding:0.6b`, OpenAI `text-embedding-3-small`) |
| `ITS_EMBED_QUERY_PREFIX` | Instruktion vor Suchanfragen (Standard bei Qwen3-Embedding gesetzt, sonst leer) |
| `ITS_CHUNK_GROESSE`, `ITS_CHUNK_OVERLAP` | Chunkgrösse und Overlap in Zeichen (Standard 1200 und 300, Entscheid E6) |
| `ITS_RAG` | `auto` (Standard) oder `aus` für den ganzen Server (T-30) |
| `ITS_RAG_AB_TOKENS` | Ab welcher Materialgrösse «Materialzugriff: automatisch» Auszüge verwendet (Standard 4000 geschätzte Tokens) |
| `ITS_RAG_K`, `ITS_RAG_MAX_ZEICHEN` | Höchstzahl Auszüge und Zeichen pro Anfrage (Standard 6 und 7000) |
| `ITS_GIT_COMMIT` | Commit für die Versionsanzeige, wenn kein `.git` vorhanden ist (Docker, T-31) |
| `ITS_LOG_HEADERS_UNMASKED` | `true` zeigt Cookie, Authorization und Header mit jwt/token/secret im Namen ungekürzt (Standard `false`, Entscheid E5) |

## Tests

```bash
pip install pytest
python3 -m pytest tests/ -q
```

`tests/test_tutor.py` deckt die deterministische Adaptionslogik ab (Level rauf/runter,
Retry, Serien, Randfälle), `tests/test_api.py` testet den kompletten Lernenden-Flow
End-to-End über die API mit Mock-Provider – ohne LLM, ohne laufenden Server.

Oberflächenprüfungen mit Playwright laufen separat gegen eine eigens gestartete
Instanz mit Mock-Provider (bei Bedarf verzögert oder scheiternd):

```bash
pip install playwright && python3 -m playwright install chromium
python3 tests/ui/ui_checks.py          # alle Szenarien, oder z.B. t02 d07 t22 l01 l02 t28 t30 l04 n06
```

Für die Prüfung der Formeldarstellung (T-13) lädt das Skript KaTeX aus einem lokal
entpackten npm-Paket, wenn `ITS_KATEX_DIR` darauf zeigt (`npm pack katex@0.16.11`).

Die didaktischen Pakete lassen sich zusätzlich gegen ein echtes Sprachmodell
evaluieren (nicht Teil der normalen Testsuite, schreibt einen Bericht nach
`tests/eval/berichte/`):

```bash
python3 tests/eval/eval_didaktik.py              # alle Pakete, dauert mit qwen3:30b länger
python3 tests/eval/eval_didaktik.py D-01 --anzahl 3
python3 tests/eval/eval_didaktik.py D-07 D-08 D-09 D-10 D-11 D-12 T-09 --haftung <id-der-lektion>
python3 tests/eval/eval_didaktik.py D-13 D-14 D-15 D-16 D-17 D-18 T-09   # Auftrag 3 mit den Fällen aus Anhang B
python3 tests/eval/eval_didaktik.py D-19 D-20 D-21 --haftung <id-der-lektion>   # Auftrag 5, Bäckerei-Aufgabe
python3 tests/eval/diagnose_ollama.py            # leere Antworten und Tokenschätzung (T-08/T-09)
```

## Bewusste Grenzen (MVP)

Kein eigenes Benutzerverzeichnis (ein gemeinsames Lehrpersonen-Passwort und ein
Klassencode, optional Anmeldung über einen Proxy). RAG gibt es seit Auftrag 4 nur für
Lernmaterialien aus der Ablage und nur mit eingerichteter Vektordatenbank; Lektionen mit
eingefügtem Text arbeiten weiterhin mit dem ganzen Material. Bilder ohne Texterkennung
werden abgelegt, aber nicht indexiert.

## Vektordatenbank einrichten (T-29)

```bash
pip install -r requirements.txt               # enthält chromadb (Client und Server)
chroma run --path vektordb --port 8011        # eigener Dienst, eigenes Fenster
ollama pull qwen3-embedding:0.6b              # Embedding-Modell beim Chat-Anbieter
# .env: ITS_VEKTOR_DB_URL=http://localhost:8011
```

Auf Windows startet `start.bat` die Vektordatenbank automatisch in einem eigenen Fenster.
Mit Docker läuft sie als Dienst `chroma` (siehe `docker-compose.yml`). Den Overlap prüft
`python tests/eval/eval_chunking.py --embedder its --dateien <grosses.pdf>` mit dem echten
Embedding-Modell; der Bericht landet in `tests/eval/berichte/`.

## Versionierung (T-31)

Die Version steht in `VERSION`, die Historie in `CHANGELOG.md`. Pro Auftrag steigt die
Minor-Version, Korrekturen erhöhen die Patch-Version, 1.0.0 ist der Stand für den Pilot.
Angezeigt wird `Version+Commit`; im Container setzt man den Commit beim Bauen:
`ITS_GIT_COMMIT=$(git rev-parse --short HEAD) docker compose build`.

## Sinnvolle nächste Schritte

1. Prompts mit realen Lernenden-Antworten tunen (Bewertungsstrenge, Erklärtiefe).
2. Eigene Lektionen über den Editor erstellen und mit der Klasse testen.
3. Tutoring-Modi (erklärend, sokratisch, prüfend, coaching) aus dem Systemkonzept.
4. Overlap und Schwelle für RAG mit qwen3-embedding auf a9-mega bestätigen (`tests/eval/eval_chunking.py`).
