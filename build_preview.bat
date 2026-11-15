@echo off
rem Builds the PREVIEW app (MacroRecorder_Preview.exe + hidden _internal) into "Preview build", for
rem trying changes before they go into the real app. It uses its own settings (the "MacroRecorder
rem Preview" folder), never the real app's. Reuses the last preview build's work in Temp, so it's
rem quicker than build.bat (which always builds from scratch). "Complete build version" and
rem "Previous version" are never touched here. Add "clean" to build from scratch: build_preview.bat clean
cd /d "%~dp0"
set "PW=%TEMP%\MacroRecorder_preview_build"
set "OUT=Preview build"
if not exist "%PW%" mkdir "%PW%"
if not exist "%PW%\preview_main.py" (
  > "%PW%\preview_main.py" echo import modern_ui
  >> "%PW%\preview_main.py" echo modern_ui.main^(preview=True^)
)
set "CLEAN="
if /i "%~1"=="clean" set "CLEAN=--clean"
set "MR_ONEFILE="
set "MR_PREVIEW=%PW%"
py -m PyInstaller --noconfirm %CLEAN% --distpath "%PW%\dist" --workpath "%PW%\work" ^
  "Source code\MacroRecorder_win.spec" || goto :fail
set "MR_PREVIEW="
rem a running preview can't be replaced
tasklist /fi "imagename eq MacroRecorder_Preview.exe" 2>nul | find /i "MacroRecorder_Preview.exe" >nul && goto :locked
if not exist "%OUT%" mkdir "%OUT%"
if exist "%OUT%\_internal" rmdir /s /q "%OUT%\_internal"
if exist "%OUT%\_internal" goto :locked
robocopy "%PW%\dist\MacroRecorder_Preview" "%OUT%" /e /nfl /ndl /njh /njs /np >nul
if errorlevel 8 goto :fail
attrib +h "%OUT%\_internal" >nul 2>nul
echo.
echo Built "%OUT%\MacroRecorder_Preview.exe"
goto :eof
:locked
echo.
echo The preview is open: close Macro Recorder (Preview) and run this again.
exit /b 1
:fail
echo.
echo The preview build failed (see above).
exit /b 1
