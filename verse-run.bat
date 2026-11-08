@echo off
rem Run: verse-run <script.verse> [args...]
if not exist "%~dp0runtime\Engine\Binaries\Win64\verse.exe" (
  echo verse.exe not found. Run setup.bat first.
  exit /b 1
)
"%~dp0runtime\Engine\Binaries\Win64\verse.exe" %*
