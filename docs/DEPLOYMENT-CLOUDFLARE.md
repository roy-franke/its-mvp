# ITS über Cloudflare Tunnel veröffentlichen (tutor.casaai.me)

Das System läuft lokal auf dem eigenen PC (a9-mega), ist aber über
https://tutor.casaai.me aus dem Internet erreichbar. Der Cloudflare Tunnel
baut dafür eine ausgehende Verbindung von diesem PC zu Cloudflare auf – es
müssen keine Ports im Router geöffnet werden, und HTTPS übernimmt Cloudflare.

Voraussetzung: Cloudflare-Account, Domain casaai.me liegt bei Cloudflare.
Die Subdomain muss NICHT von Hand angelegt werden – sie entsteht automatisch,
sobald der Public Hostname im Tunnel eingetragen wird (Schritt 4).

## Ist-Zustand auf a9-mega (eingerichtet am 28.8.2026)

Ein einziger Tunnel namens `a9-mega`, dashboard-verwaltet, mit zwei Routen:
tutor.casaai.me auf http://localhost:8010 (ITS) und ollix-free.casaai.me auf
http://localhost:8000. Der cloudflared-Dienst läuft als Windows-Dienst und
startet mit dem PC. Die früheren Tunnel `tutor`, `ollix-free` und `ollama`
wurden gelöscht; der erste war lokal per config.yml verwaltet und liess sich
im Dashboard nicht erweitern.

## Schritt 1: Zero-Trust-Dashboard öffnen

1. https://one.dash.cloudflare.com öffnen und anmelden.
2. Links im Menü: **Networks → Tunnels**.

Falls hier schon ein Tunnel für diesen PC existiert (von einer anderen
Applikation): Schritte 2 und 3 überspringen und beim bestehenden Tunnel nur
den zusätzlichen Public Hostname eintragen (Schritt 4). Pro PC läuft
üblicherweise ein cloudflared-Dienst, der beliebig viele Hostnamen bedient.
Läuft der Tunnel der anderen App auf einem anderen Rechner, braucht dieser PC
einen eigenen Tunnel – dann normal weiter mit Schritt 2.

## Schritt 2: Tunnel erstellen

1. **Create a tunnel** → Typ **Cloudflared** → Name z.B. `a9-mega` → Save.
2. Auf der nächsten Seite als Betriebssystem **Windows (64-bit)** wählen.
3. Cloudflare zeigt einen Befehl an, der so beginnt:
   `cloudflared.exe service install eyJhIjo...`
   Diesen Befehl mit dem Kopier-Symbol kopieren. Der lange Teil ist das
   Tunnel-Token – es gehört nur in dieses Fenster, nicht in Chats oder Mails.

## Grundregel: ein Tunnel pro PC, beliebig viele Hostnamen

Auf einem Rechner läuft genau ein cloudflared-Dienst, und dieser Dienst gehört
zu genau einem Tunnel. Mehrere Anwendungen gleichzeitig zu veröffentlichen ist
trotzdem kein Problem: Ein Tunnel kann beliebig viele Public Hostnames haben,
die je auf einen anderen lokalen Port zeigen.

| Hostname | Service-URL | Anwendung |
|---|---|---|
| tutor.casaai.me | http://localhost:8010 | ITS-MVP |
| ollix-free.casaai.me | http://localhost:8000 | ollix |

**Jede Anwendung braucht einen eigenen Port.** Zwei Programme können nicht
denselben Port belegen. Das ITS läuft deshalb auf 8010 (in `start.bat`
festgelegt), Port 8000 bleibt für die andere Anwendung frei.

**Dashboard-verwaltet statt lokal:** Zeigt ein Tunnel im Dashboard den Hinweis
«This tunnel is locally managed», bezieht er seine Routen aus einer config.yml
auf dem PC, und «Add route» ist gesperrt. Für den Betrieb mehrerer Anwendungen
ist ein dashboard-verwalteter Tunnel bequemer, weil alles im Browser
einstellbar bleibt. Ein Tunnel, dessen Connector mit `service install TOKEN`
eingerichtet wurde, ist automatisch dashboard-verwaltet.

Ein zweiter Tunnel für dieselbe Maschine bringt nichts – er bliebe «Inactive»,
weil kein Connector zu ihm gehört. Wer bereits mehrere Tunnel angelegt hat,
konsolidiert sie: alle Hostnamen auf den Tunnel legen, dessen Dienst läuft, und
die übrigen Tunnel löschen.

**Achtung Reihenfolge:** Ein Hostname kann immer nur auf einen Tunnel zeigen.
Also zuerst den alten Tunnel (samt Route) löschen, danach die Route beim
Ziel-Tunnel neu anlegen.

**Sicherheitshinweis:** Der Token im Installationsbefehl ist ein Geheimnis. Ist
er einmal sichtbar geworden (Screenshot, Chat, Mail), gilt er als kompromittiert
und muss ersetzt werden – am einfachsten, indem der Tunnel gelöscht und neu
angelegt wird.

## Schritt 3: cloudflared auf dem PC als Dienst installieren

1. Windows-Taste drücken, «powershell» tippen, dann **Strg+Shift+Enter** –
   das erzwingt Administratorrechte. In der Titelleiste des Fensters muss
   «Administrator» stehen. Im Zweifel prüfen mit:
   ```powershell
   ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
   ```
   Kommt `False`, ist das Fenster nicht erhöht; Dienstbefehle scheitern dann
   mit «Cannot establish a connection to the service control manager: Access
   is denied».
2. cloudflared installieren:
   ```powershell
   winget install --id Cloudflare.cloudflared
   ```
   (Falls winget fehlt: Installer von
   https://github.com/cloudflare/cloudflared/releases herunterladen.)
3. PowerShell schliessen und als Administrator neu öffnen (damit der Pfad
   aktuell ist), dann den kopierten Befehl aus Schritt 2 einfügen und
   ausführen:
   ```powershell
   cloudflared.exe service install eyJhIjo...   # dein kopierter Befehl
   ```
4. Zurück im Browser: Cloudflare meldet unten «Connectors: 1 Connector» –
   der PC ist verbunden. Der Dienst startet ab jetzt automatisch mit Windows.

## Schritt 4: Public Hostname eintragen (erstellt die Subdomain)

Im Tunnel auf **Public Hostname** → **Add a public hostname**:

| Feld | Wert |
|---|---|
| Subdomain | `tutor` |
| Domain | `casaai.me` |
| Type | `HTTP` |
| URL | `localhost:8010` |

Weitere Anwendungen kommen als zusätzliche Public Hostnames auf denselben
Tunnel, je mit ihrem eigenen Port.

Speichern. Cloudflare legt damit automatisch den DNS-Eintrag für
tutor.casaai.me an.

**Wichtig – häufigster Fehler:** Die Service-URL muss `http://localhost:8010`
lauten, nicht `https://`. Gemeint ist die lokale Verbindung vom Tunnel zur App
auf demselben PC, und die läuft unverschlüsselt. Nach aussen liefert Cloudflare
trotzdem HTTPS. Steht dort `https://`, quittiert der Tunnel jede Anfrage mit
einem Fehler 502.

## Schritt 5: Testen

1. Auf dem PC das ITS starten: Doppelklick auf `start.bat` im Projektordner.
2. https://tutor.casaai.me im Browser öffnen – am besten zusätzlich auf dem
   Handy über Mobilfunk, dann ist der Zugriff wirklich «von aussen» getestet.
3. Lernenden-Ansicht: Zugangscode-Feld muss erscheinen (CLASS_CODE aus der
   `.env`). https://tutor.casaai.me/teacher muss auf die Login-Seite führen.

## Betrieb

- Der Tunnel läuft immer (Windows-Dienst). Erreichbar ist das ITS aber nur,
  solange auf dem PC der Server läuft (`start.bat`-Fenster offen) – Fenster
  schliessen beendet den Zugriff. Für Ollama gilt dasselbe: Die Ollama-App
  muss laufen, sonst antwortet der Tutor mit Fallback-Texten.
- Zugangsdaten stehen in der `.env` (TEACHER_PASSWORD für /teacher,
  CLASS_CODE für Lernende). Nach jeder Änderung an der `.env` den Server neu
  starten. Ein Passwortwechsel meldet alle Lehrpersonen automatisch ab.
- Tunnel vorübergehend abschalten: Windows-Dienste öffnen (Windows-Taste,
  «Dienste» tippen), Dienst «cloudflared» stoppen. Oder im
  Cloudflare-Dashboard den Public Hostname löschen.
- Status prüfen: Networks → Tunnels zeigt, ob der Connector verbunden ist.

## Stolpersteine

- **Fehler 502 Bad Gateway** auf tutor.casaai.me: Der Tunnel steht, aber die
  App läuft nicht → `start.bat` starten.
- **Merkregel zu den Fehlernummern**: 1033 heisst, der Tunnel-Dienst läuft
  nicht (Cloudflare findet keinen Connector). 502 heisst, der Tunnel steht,
  aber die App dahinter läuft nicht. Für den Betrieb müssen beide laufen:
  `start.bat` für das ITS und der Windows-Dienst Cloudflared für den Tunnel.
  `start.bat` warnt beim Start, wenn der Dienst fehlt.
- **Dienst startet nicht automatisch mit Windows**: Starttyp einmalig setzen
  mit `Set-Service Cloudflared -StartupType Automatic` in einer
  Administrator-PowerShell, danach `Start-Service Cloudflared`.
- **Fehler 1033 (Cloudflare Tunnel error)**: Der Hostname existiert, aber es
  ist kein Connector verbunden. Im Dashboard steht der Tunnel dann auf
  «Inactive» oder «Down» mit 0 Replicas. Heisst: cloudflared läuft auf dem PC
  nicht. Prüfen mit `Get-Service cloudflared` in einer Administrator-PowerShell;
  fehlt der Dienst, ist Schritt 3 nicht durchgelaufen.
- **«cloudflared service is already installed»**: Es existiert bereits ein
  Dienst für einen anderen Tunnel. Entweder den gewünschten Hostname beim
  bestehenden Tunnel eintragen (empfohlen, siehe Grundregel oben), oder den
  alten Dienst mit `cloudflared service uninstall` entfernen und danach neu
  installieren.
- **«Access is denied» bei service install/uninstall**: Die PowerShell läuft
  nicht als Administrator. Fenster mit Strg+Shift+Enter neu öffnen (siehe
  Schritt 3).
- **Dienst hängt in «StopPending»**: `Get-Service Cloudflared` zeigt
  StopPending und nichts geht mehr weiter. Prozess hart beenden mit
  `Get-Process cloudflared | Stop-Process -Force`, danach prüfen mit
  `sc.exe queryex Cloudflared`. Meldet der Befehl, dass der Dienst nicht
  existiert, ist alles in Ordnung und die Neuinstallation kann folgen. Zur Not
  hilft ein Neustart des PCs.
- **Fehler 530 / Tunnel not found**: cloudflared-Dienst läuft nicht →
  Windows-Dienste prüfen oder PC neu starten.
- **Seite lädt, aber Tutor antwortet generisch**: Ollama läuft nicht oder
  falsches Modell in der `.env` → auf dem PC http://localhost:8010/api/llm-test
  aufrufen.
- Der PC darf nicht in den Ruhezustand gehen, solange Lernende arbeiten
  (Windows-Einstellungen → Energie: Ruhezustand auf «Nie» im Netzbetrieb).

## Hinweis Datenschutz

Für Tests und Demos mit fiktiven Namen ist dieses Setup unbedenklich.
Für den Pilot mit echten Lernenden gilt weiterhin der Plan aus dem
Systemkonzept: Betrieb on-premise (RIB-AI-01), Pseudonyme, und die
Zugangsdaten nur der Klasse mitteilen.
