@echo off
rem First run: fetch UE source and build only the Verse tools (setup --help for options)
python -I "%~dp0tools\setup.py" %*
