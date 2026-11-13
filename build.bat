@echo off
rem Builds MacroRecorder.exe, a single file that runs without Python, and puts it in
rem "Complete build version". PyInstaller's working files go to your Temp folder.
cd /d "%~dp0"
set "WORK=%TEMP%\MacroRecorder_build"
set "OUT=Complete build version"
py -m pip install -q --upgrade pyinstaller -r "Source code\requirements.txt" || goto :fail
rem the recipe (what goes into the exe, and what's left out) is in Source code\MacroRecorder_win.spec
set "MR_PREVIEW="
py -m PyInstaller --noconfirm --clean --distpath "%WORK%\dist" --workpath "%WORK%\work" ^
  "Source code\MacroRecorder_win.spec" || goto :fail
if not exist "%OUT%" mkdir "%OUT%"
rem keep the version that's being replaced in "Previous version", to go back to it if needed
if exist "%OUT%\MacroRecorder.exe" (
  if not exist "Previous version" mkdir "Previous version"
  copy /y "%OUT%\MacroRecorder.exe" "Previous version\MacroRecorder.exe" >nul
)
copy /y "%WORK%\dist\MacroRecorder.exe" "%OUT%\MacroRecorder.exe" >nul || goto :locked
echo.
echo Built "%OUT%\MacroRecorder.exe"
goto :eof
:locked
echo.
echo The build worked, but "%OUT%\MacroRecorder.exe" couldn't be replaced because it's
echo running. Close Macro Recorder and run build.bat again.
pause
exit /b 1
:fail
echo Build failed.
pause
exit /b 1
