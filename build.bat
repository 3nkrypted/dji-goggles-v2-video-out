@echo off
setlocal

REM Build standalone dji_capture.exe with PyInstaller
REM This bundles Python code and dependencies (pyusb, numpy, opencv, libusb_package).

if "%VIRTUAL_ENV%"=="" (
    echo (Optional) You may want to activate your virtualenv before building.
)

echo Installing PyInstaller (if not already installed)...
python -m pip install --upgrade pyinstaller >nul

echo Building dji_capture.exe with PyInstaller...
pyinstaller --onefile --name dji_capture ^
    --hidden-import=libusb_package ^
    dji_capture.py

if errorlevel 1 (
    echo PyInstaller build failed.
    goto :end
)

REM Try to bundle ffmpeg.exe alongside the built EXE so it's available at runtime.
echo Checking for ffmpeg on PATH...
where ffmpeg >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "delims=" %%F in ('where ffmpeg') do (
        echo Copying ffmpeg from %%F to dist\ffmpeg.exe
        copy "%%F" "dist\ffmpeg.exe" /Y >nul
        goto :after_ffmpeg
    )
) else (
    echo ffmpeg not found on PATH. The generated EXE will require ffmpeg to be installed.
    echo At runtime, dji_capture.exe will look for 'ffmpeg' in the same folder or on PATH.
)

:after_ffmpeg
echo.
echo Build complete.
echo You can run the app from: dist\dji_capture.exe
echo Make sure ffmpeg.exe is either in the same folder or on PATH.

:end
endlocal

