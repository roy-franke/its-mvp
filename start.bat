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

echo Server laeuft gleich auf http://localhost:8010
echo Lernende:   http://localhost:8010/
echo Lehrperson: http://localhost:8010/teacher
echo Dieses Fenster offen lassen. Beenden mit Ctrl+C oder Fenster schliessen.
echo.
start "" http://localhost:8010
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8010
pause
