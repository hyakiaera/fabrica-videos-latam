@echo off
REM Fabrica de videos - modo PC (Windows)
REM Doble clic: instala lo necesario la primera vez y trabaja cada 4 horas
REM mientras la computadora este prendida. Cierra la ventana para parar.
cd /d "%~dp0"
if not exist .venv (
  echo Instalando por primera vez, puede tardar unos minutos...
  python -m venv .venv || (echo Necesitas Python 3.11 o mas nuevo: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install -q -r requirements.txt
  .venv\Scripts\python -m pip install -q --no-deps gTTS
)
if not exist config.toml copy config.example.toml config.toml >nul
if not exist fabrica.toml copy fabrica.example.toml fabrica.toml >nul
.venv\Scripts\python -m fabrica --repetir-cada 4 %*
pause
