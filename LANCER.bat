@echo off
REM Script de lancement rapide pour FixPro
REM Simplement double-cliquez sur ce fichier!

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║         FixPro - Lancement Automatique                 ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Aller dans le dossier courant
cd /d "%~dp0"

REM Activer l'environnement virtuel
call .venv\Scripts\Activate.bat

REM Vérifier la configuration
echo.
echo 🔍 Vérification de la configuration...
echo.

python check.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ Configuration incomplète. Consultez DEPANNAGE.md
    pause
    exit /b 1
)

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║     Que voulez-vous faire?                             ║
echo ╚════════════════════════════════════════════════════════╝
echo.
echo 1 - Menu interactif (FixPro test.py)
echo 2 - API web (app.py)
echo 3 - Tests API (test_api.py)
echo 4 - Quitter
echo.

set /p choix="Choisissez (1-4): "

if "%choix%"=="1" (
    echo.
    echo Lancement du menu interactif...
    echo.
    python "FixPro test.py"
) else if "%choix%"=="2" (
    echo.
    echo Lancement de l'API web sur http://localhost:5000
    echo Appuyez sur Ctrl+C pour arrêter
    echo.
    python app.py
) else if "%choix%"=="3" (
    echo.
    echo Lancement des tests...
    echo.
    python test_api.py
) else (
    echo Bye!
    exit /b 0
)

pause
