@echo off
rem Builds MacroRecorder.exe, a single file that runs without Python, and puts it in
rem "Complete build version". PyInstaller's working files go to your Temp folder.
cd /d "%~dp0"
set "WORK=%TEMP%\MacroRecorder_build"
set "OUT=Complete build version"
py -m pip install -q --upgrade pyinstaller -r "Source code\requirements.txt" || goto :fail
py -m PyInstaller --noconfirm --clean --onefile --windowed --name MacroRecorder ^
  --distpath "%WORK%\dist" --workpath "%WORK%\work" --specpath "%WORK%" ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  --add-data "%~dp0Source code\retry_default.png;." ^
  "Source code\macro_recorder.py" || goto :fail
if not exist "%OUT%" mkdir "%OUT%"
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
