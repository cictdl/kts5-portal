@echo off
rem KTS 5.0 server probe: find a Python 3 interpreter and start probe.py with it.
rem Everything it learns is written to probe-result.txt next to this file.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
> probe-result.txt echo probe.cmd started in %CD% as %USERNAME% on %DATE% %TIME%
set "PY="
for /f "delims=" %%i in ('where python.exe 2^>nul') do (
  if not defined PY (
    set "CAND=%%i"
    rem skip the Microsoft Store placeholder stub
    if "!CAND:WindowsApps=!"=="!CAND!" set "PY=%%i"
  )
)
if not defined PY (
  for %%d in ("C:\Python313" "C:\Python312" "C:\Python311" "C:\Python310" "C:\Program Files\Python313" "C:\Program Files\Python312" "C:\Program Files\Python311" "C:\Program Files\Python310" "C:\Program Files\Python39" "%LocalAppData%\Programs\Python\Python313" "%LocalAppData%\Programs\Python\Python312" "%LocalAppData%\Programs\Python\Python311" "C:\Program Files (x86)\Plesk\Additional\Python" "C:\Program Files (x86)\Parallels\Plesk\Additional\Python") do (
    if not defined PY if exist "%%~d\python.exe" set "PY=%%~d\python.exe"
  )
)
if not defined PY (
  >> probe-result.txt echo RESULT: Python was not found on this server. PATH and the usual folders were checked.
  >> probe-result.txt echo Ask the hosting administrator to install Python 3.11 or newer for all users with "Add python.exe to PATH".
  exit /b 1
)
>> probe-result.txt echo RESULT: Python found at !PY!
"!PY!" -c "import sys; print('version', sys.version)" >> probe-result.txt 2>&1
>> probe-result.txt echo starting probe.py on port %HTTP_PLATFORM_PORT%
"!PY!" probe.py >> probe-result.txt 2>&1
