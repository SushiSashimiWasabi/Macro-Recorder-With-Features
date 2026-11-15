@echo off
rem Builds Macro Recorder (runs without Python) into "Complete build version": MacroRecorder.exe and
rem a hidden folder _internal beside it (the folder build: it starts in about a second, because
rem there's nothing to unpack). Keep the two together. PyInstaller's working files go to Temp.
rem For the old one-file exe instead: set MR_ONEFILE=1 before running this (GitHub builds both).
cd /d "%~dp0"
set "WORK=%TEMP%\MacroRecorder_build"
set "OUT=Complete build version"
set "PREV=Previous version"
py -m pip install -q --upgrade pyinstaller -r "Source code\requirements.txt" || goto :fail
rem the recipe (what goes into the app, and what's left out) is in Source code\MacroRecorder_win.spec
set "MR_PREVIEW="
py -m PyInstaller --noconfirm --clean --distpath "%WORK%\dist" --workpath "%WORK%\work" ^
  "Source code\MacroRecorder_win.spec" || goto :fail
rem a running Macro Recorder can't be replaced
tasklist /fi "imagename eq MacroRecorder.exe" 2>nul | find /i "MacroRecorder.exe" >nul && goto :locked
if not exist "%OUT%" mkdir "%OUT%"
rem keep the version that's being replaced in "Previous version", to go back to it if needed
if exist "%OUT%\MacroRecorder.exe" (
  if not exist "%PREV%" mkdir "%PREV%"
  if exist "%OUT%\_internal" (
    rem the folder build: packed into one zip (about 60 MB instead of 150 MB)
    if exist "%PREV%\MacroRecorder.zip" del /q "%PREV%\MacroRecorder.zip"
    tar -a -c -f "%PREV%\MacroRecorder.zip" -C "%OUT%" MacroRecorder.exe _internal || goto :fail
    if exist "%PREV%\MacroRecorder.exe" del /q "%PREV%\MacroRecorder.exe"
  ) else (
    copy /y "%OUT%\MacroRecorder.exe" "%PREV%\MacroRecorder.exe" >nul
  )
)
if defined MR_ONEFILE (
  copy /y "%WORK%\dist\MacroRecorder.exe" "%OUT%\MacroRecorder.exe" >nul || goto :locked
  echo.
  echo Built "%OUT%\MacroRecorder.exe" ^(one file^)
  goto :eof
)
if exist "%OUT%\_internal" rmdir /s /q "%OUT%\_internal"
if exist "%OUT%\_internal" goto :locked
if exist "%OUT%\MacroRecorder.exe" del /q "%OUT%\MacroRecorder.exe"
robocopy "%WORK%\dist\MacroRecorder" "%OUT%" /e /nfl /ndl /njh /njs /np >nul
if errorlevel 8 goto :fail
attrib +h "%OUT%\_internal"
echo.
echo Built "%OUT%\MacroRecorder.exe" (with its hidden _internal folder)
goto :eof
:locked
echo.
echo The build worked, but Macro Recorder in "%OUT%" couldn't be replaced because it's
echo running. Close Macro Recorder and run build.bat again.
pause
exit /b 1
:fail
echo Build failed.
pause
exit /b 1
