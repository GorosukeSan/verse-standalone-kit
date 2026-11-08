@echo off
rem Check the build environment (--check-access also checks GitHub access)
python -I "%~dp0tools\doctor.py" %*
