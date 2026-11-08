@echo off
rem Type check: verse-check <folder or .verse> [--profile cmd^|uefn^|fortnite]
python -I "%~dp0tools\verse_check.py" %*
