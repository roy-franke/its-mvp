# Auftrag 5: Anpassungen nach dem Test vom 20.10.2026

Grundlage: Auftragsdokument «Anpassungen ITS-Prototyp nach dem Test vom 20.10.2026» vom 22.10.2026 zum
Feedback «Prototyp Roy 2026-10-20 Feedback.docx» (Stand 0.5.0, Lektion «Haftungsrecht: Unerlaubte Handlungen
Version 3»). Ausgangsstand `7301063`, Ergebnis Version 0.6.0. Umgesetzt sind genau die fünf Pakete; was das
Dokument ausschliesst, ist nicht umgesetzt.

## 1. Pakete

| Reihenfolge | Paket | Thema | Feedback-Punkt | Priorität |
|---|---|---|---|---|
| 1 | D-19 | Erwartete Begründungstiefe passt zur Frage | Lernenden-Teil 1 | Must |
| 2 | D-20 | Sinngleiche Formulierungen werden akzeptiert | Lernenden-Teil 2 | Must |
| 3 | D-21 | Hinweis verrät die erwartete Antwort nicht | Lernenden-Teil 3 | Must |
| 4 | L-04 | Archivierte Lektionen nicht bearbeitbar | Lehrpersonen-Teil 1 | Must |
| 5 | N-06 | Teaching Mode für Lektionen | Grundsätzliches 1 | Should |

## 2. Entscheide

Die Spalte «Entscheid» im Auftragsdokument war leer, es gelten die Vorschläge.

| Nr. | Entscheid |
|---|---|
| E1 | D-21 gilt für Hinweis und Feedbacktext derselben Rückmeldung. |
| E2 | Jeder Weg in den Editor ist für archivierte Lektionen zu: kein «Bearbeiten», der direkte Aufruf zeigt eine Meldung statt des Formulars, die Materialdetails verlinken archivierte Lektionen nicht. Duplizieren und Wiederherstellen bleiben wie bisher. |
| E3 | N-06 ist umgesetzt, als letztes Paket und in einem eigenen Commit. Eine getrennte Abnahme von D-19 bis L-04 vor N-06 gab es nicht, weil der Auftrag in einem Durchgang erteilt wurde; N-06 lässt sich bei Bedarf einzeln zurücknehmen. Die lektionsübergreifende Verbesserung ist nicht umgesetzt. |
| E4 | Start über «Im Teaching Mode testen» in der Lektionsverwaltung; der normale Testlauf bleibt unverändert. |
| E5 | «Nur für dieses Thema» hängt am Feld `konzept` des Schritts und wirkt in allen Anfragen zu diesem Konzept (Vergleich mit `didaktik.gleiches_konzept`). |
| E6 | «Für die ganze Lektion» lässt den Tutor eine allgemeine Fassung vorschlagen; die Lehrperson ändert sie bei Bedarf und bestätigt sie. |
| E7 | Eigene Liste `tutor_anweisungen` in der Lektion, getrennt von `tutor_hinweise`. Der Editor zeigt sie und löscht einzelne Einträge; Speichern und Löschen erhöhen die Version. |
| E8 | Wirkung ab dem nächsten Aufruf des Tutors in dieser Lektion, auch in laufenden Sequenzen anderer Personen. Der aktuelle Schritt wird nicht neu erzeugt. |
| E9 | Jede Lehrperson für jede nicht archivierte Lektion, ohne Besitzermodell. |

## 3. Umsetzung und Auslegung

**D-19.** Der Befund liess sich mit der Aufgabe aus der its.db nicht belegen, weil sie nicht vorlag (siehe
Abschnitt 5). Aus dem Code: Die Bewertung erhält zu jedem Element den erwarteten Inhalt in der Tiefe der
Musterlösung («Art der Haftung – erwartet: Haftung für Fahrlässigkeit …»), und «ungenau» hiess «zu allgemein».
Neu misst die Bewertung jedes Element an der Tiefe, die die Frage erkennbar verlangt (`tutor.TIEFE_DER_FRAGE`,
fachneutral), «ungenau» heisst «allgemeiner, als die Frage es verlangt», und die Aufgabe legt den erwarteten
Inhalt in der Tiefe der Frage fest. Texte zur Bewertungsstrenge, Urteilslogik und Frageformulierung sind
unverändert; die Analyse zeigte keinen Bedarf, sie zu ändern, weil die Strenge «ausgewogen» ausdrücklich vom
Begriff spricht, der «gefragt ist».

**D-20.** Regel im Bewertungsprompt (`tutor.GLEICHE_BEDEUTUNG`) für alle drei Strengen und Prüfung
`didaktik.fachbegriff_trotzdem_ungenau`: Ist ein Element ungenau, obwohl alle Stämme eines erwarteten
Fachbegriffs in der Antwort zu diesem Element stehen, folgt ein Korrekturhinweis. Erwartete Fachbegriffe sind
die Schlüsselbegriffe der Aufgabe, die im erwarteten Inhalt des Elements stehen. Der vorhandene Wortvergleich
wird gerichtet genutzt: Der Stamm des Begriffs muss in einem gleich langen oder längeren Wort der Antwort stehen
(«fahrlässig» in «Fahrlässigkeitshaftung»), nicht umgekehrt («schuld» ist nicht «Verschuldenshaftung»).

**D-21.** Prüfung `didaktik.loesung_verraten` für Feedback und Hinweis. Gesperrt sind die Stämme ab fünf
Zeichen aus den Schlüsselbegriffen und aus dem erwarteten Inhalt der noch nicht erfüllten Elemente, ausser sie
stehen in Titel, Fall oder Frage oder in einer Antwort der lernenden Person (auch einem früheren Versuch).
Ein Schlüsselbegriff, der nur zu erfüllten Elementen gehört, bleibt frei, damit «vertretbar» weiterhin die
naheliegendere Lösung zeigen kann (D-15). Ein Treffer führt zum Korrekturhinweis; bleibt er bestehen, ersetzt
`tutor.hinweis_ohne_loesung` den Hinweis (geprüft ohne gesperrte Stämme), und aus dem Feedback fallen die Sätze
mit gesperrten Stämmen weg (bleibt nichts, ein neutraler Satz). Die Kürzung des Feedbacks ist die
Entsprechung zum Ersatzhinweis für den Feedbacktext (E1); das Dokument nennt den Ersatz nur für den Hinweis.

**L-04.** Siehe Abschnitt 5 zum Befund. Der Editor blendet bei einer archivierten Lektion das Formular aus und
zeigt «Die Lektion ist archiviert. Stelle sie zuerst wieder her, um sie zu bearbeiten.» mit Link zur
Lektionsliste; die Materialdetails zeigen archivierte Lektionen ohne Link. Der Server lehnte das Speichern
schon ab; ein Test belegt, dass die Datei dabei unverändert bleibt.

**N-06.** Der Teaching Mode ist ein Testlauf mit der zusätzlichen Spalte `sessions.teaching` (Migration,
Standard 0). Anweisungen nimmt nur die Lehrperson in ihrer eigenen Teaching-Sequenz an, für nicht archivierte
Lektionen. Anweisungen für die Lektion stehen am Ende des Systemprompts, der damit innerhalb der Lektion für
alle Schrittarten gleich bleibt. Anweisungen zu einem Thema hängt `tutor._chat` an den Benutzerteil, wenn das
Konzept des Schritts vor dem Aufruf feststeht: Bewertung, Gegenprüfung, Verständnisfragen, Erklärungen zu
einem bestimmten Konzept und Aufgaben direkt nach einer Theorie oder als Vereinfachung. Die Verallgemeinerung
ist ein eigener Aufruf (`ANWEISUNG_VERALLGEMEINERN`) ohne Lektionsmaterial; im Fallback erhält die
Lehrperson ihren eigenen Text. «Teach the Tutor» steht unter jeder Nachricht des Tutors, bei einer Aufgabe
unter der Frage.

## 4. Grenzen

- Führt eine Theorie oder eine Aufgabe ein neues Konzept ein, das der Tutor selbst wählt, steht das Konzept
  vor dem Aufruf nicht fest; Anweisungen zu einem Thema wirken dort nicht, wohl aber in allen folgenden
  Schritten zu diesem Konzept.
- Ein Schritt, der beim Speichern einer Anweisung schon vorgeladen war (Vorabruf), entstand ohne sie (E8:
  ab dem nächsten Aufruf).
- Die Akzeptanzkriterien mit dem echten Modell (D-19 AK 1, D-20 AK 1 und 2, D-21 AK 1 und 3, D-19 AK 5 für die
  bestehenden Szenarien) liessen sich aus der Arbeitsumgebung nicht prüfen; Ollama auf a9-mega ist von dort
  nicht erreichbar. Befehl: `.venv\Scripts\python.exe tests\eval\eval_didaktik.py D-19 D-20 D-21 --haftung
  <id-der-version-3>` und für AK 5 von D-19 die Pakete D-13 bis D-18.

## 5. Befunde zu den bereitgestellten Unterlagen

Auf a9-mega steht `Documents\its-mvp` auf `7301063` (letzter `git pull` am 15.10.2026; der Arbeitsbaum
unterscheidet sich nur in den Zeilenenden). Die dortige `its.db` wurde zuletzt am 15.10.2026 geschrieben und
enthält sieben Sequenzen bis zum 4.9.2026, `app/lessons` enthält die Lektion «Version 3» nicht. Der Test vom
20.10.2026 lief also gegen eine andere Instanz oder mit anderen Datenpfaden (etwa Windows-Umgebungsvariablen
`ITS_DB_PATH`, `ITS_LESSONS_DIR`). Die Lektion und die Lernsequenz mit der Bäckerei-Aufgabe lagen deshalb
nicht vor. Sachverhalt, Musterlösung und Elemente der Bäckerei-Aufgabe in `tests/daten/baeckerei.json` sind
rekonstruiert; Titel, Frage und Antworten stammen aus dem Auftragsdokument.

Für L-04 geprüft: Im Stand `7301063` fehlt «Bearbeiten» bei archivierten Lektionen, und PUT antwortet mit 409.
Der direkte Aufruf der Editor-Adresse zeigte das Formular, das Speichern scheiterte aber mit einer Meldung;
ebenso, wenn eine Lektion archiviert wird, während der Editor offen ist (Playwright `l04`). Am besten passt
zum beobachteten Verhalten «Duplizieren» bei einer archivierten Lektion: Es öffnet die Kopie im Editor, das
Speichern erhöht deren Version, und das Original bleibt archiviert. Das ist nach E2 unverändert.
