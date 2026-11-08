@echo off
rem Pre-release check: make sure nothing that must not be distributed is in Git
python -I "%~dp0tools\release_check.py" %*
