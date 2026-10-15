@echo off
rem === ITS-MVP: Server starten ===
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: .venv fehlt. Bitte zuerst setup.bat ausfuehren.
    pause
    exit /b 1
)

rem Tunnel-Dienst pruefen: ohne ihn ist tutor.casaai.me nicht erreichbar
sc query Cloudflared | find "RUNNING" >nul 2>nul
if errorlevel 1 (
    echo ---------------------------------------------------------------
    echo HINWEIS: Der Cloudflare-Tunnel laeuft nicht.
    echo Lokal ueber http://localhost:8010 funktioniert alles,
    echo aber https://tutor.casaai.me zeigt Fehler 1033.
    echo.
    echo Zum Starten: PowerShell als Administrator oeffnen
    echo Windows-Taste, "powershell" tippen, Strg+Shift+Enter
    echo dann eingeben:  Start-Service Cloudflared
    echo ---------------------------------------------------------------
    echo.
)

rem Umgebungsvariablen von Windows haben Vorrang vor der .env (load_dotenv
rem ueberschreibt nichts). Ein leeres TEACHER_PASSWORD in den Windows-
rem Einstellungen wuerde den Login still abschalten.
if defined TEACHER_PASSWORD (
    echo ---------------------------------------------------------------
    echo HINWEIS: TEACHER_PASSWORD ist in den Windows-Umgebungsvariablen
    echo gesetzt und hat Vorrang vor dem Wert in der .env-Datei.
    echo ---------------------------------------------------------------
    echo.
)

rem T-29: Vektordatenbank (ChromaDB) als eigener Dienst in einem eigenen Fenster.
rem Wirkt nur mit ITS_VEKTOR_DB_URL=http://localhost:8011 in der .env.
rem Laeuft sie schon, meldet das zweite Fenster «Adresse belegt»; das ist harmlos.
if exist ".venv\Scripts\chroma.exe" (
    start "ITS Vektordatenbank" ".venv\Scripts\chroma.exe" run --path vektordb --port 8011
)

echo Server laeuft gleich auf http://localhost:8010
echo Lernende:   http://localhost:8010/
echo Lehrperson: http://localhost:8010/teacher
echo Dieses Fenster offen lassen. Beenden mit Ctrl+C oder Fenster schliessen.
echo.
start "" http://localhost:8010
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8010
pause
