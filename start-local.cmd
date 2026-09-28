@echo off
rem Start the KTS 5.0 portal on this PC and open it in the browser.
rem Close this window to stop the portal.
cd /d "%~dp0"
set KTS_HOST=127.0.0.1
set KTS_PORT=8905
set PYTHONIOENCODING=utf-8
title KTS 5.0 portal - http://127.0.0.1:8905
echo Starting the KTS 5.0 portal at http://127.0.0.1:8905 ...
start "" "http://127.0.0.1:8905/"
python serve.py
pause
