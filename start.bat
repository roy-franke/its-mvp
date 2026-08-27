@echo off
rem === ITS-MVP: Server starten ===
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo FEHLER: .venv fehlt. Bitte zuerst setup.bat ausfuehren.
    pause
    exit /b 1
)

echo Server laeuft gleich auf http://localhost:8000
echo Lernende:   http://localhost:8000/
echo Lehrperson: http://localhost:8000/teacher
echo Dieses Fenster offen lassen. Beenden mit Ctrl+C oder Fenster schliessen.
echo.
start "" http://localhost:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
pause
