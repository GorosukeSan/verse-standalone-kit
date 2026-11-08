@echo off
rem Fetch the latest UE source and rebuild
python -I "%~dp0tools\setup.py" --update %*
