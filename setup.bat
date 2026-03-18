@echo off
setlocal enabledelayedexpansion

echo.
echo  DupeFinder Setup
echo  ----------------------------------------
echo.

set "BASE=%~dp0"
set "PYTHON_DIR=%BASE%python"
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
set "PYTHON_VERSION=3.13.3"
set "PYTHON_ZIP=python-%PYTHON_VERSION%-embed-amd64.zip"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_ZIP%"
set "PTH_FILE=%PYTHON_DIR%\python313._pth"

:: ----------------------------------------------------------------
:: Step 1: Download and extract embedded Python if not present
:: ----------------------------------------------------------------
if exist "%PYTHON_EXE%" (
    echo  [OK] Python already installed in python\ folder.
) else (
    echo  Downloading Python %PYTHON_VERSION% embeddable...
    echo  URL: %PYTHON_URL%
    echo.

    curl -L -o "%BASE%%PYTHON_ZIP%" "%PYTHON_URL%"
    if errorlevel 1 (
        echo.
        echo  [ERROR] Download failed. Check your internet connection.
        echo  You can also download manually from:
        echo    %PYTHON_URL%
        echo  and extract to: %PYTHON_DIR%\
        goto :error
    )

    echo  Extracting...
    mkdir "%PYTHON_DIR%" 2>nul
    powershell -Command "Expand-Archive -Path '%BASE%%PYTHON_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
    if errorlevel 1 (
        echo  [ERROR] Extraction failed.
        goto :error
    )

    del "%BASE%%PYTHON_ZIP%" 2>nul
    echo  [OK] Python extracted to python\ folder.
)

:: ----------------------------------------------------------------
:: Step 2: Enable pip by modifying the ._pth file
:: ----------------------------------------------------------------
if exist "%PTH_FILE%" (
    findstr /C:"import site" "%PTH_FILE%" >nul 2>&1
    if errorlevel 1 (
        echo import site>> "%PTH_FILE%"
        echo  [OK] Enabled site-packages in Python.
    ) else (
        :: Check if it's commented out
        findstr /B /C:"#import site" "%PTH_FILE%" >nul 2>&1
        if not errorlevel 1 (
            powershell -Command "(Get-Content '%PTH_FILE%') -replace '^#import site', 'import site' | Set-Content '%PTH_FILE%'"
            echo  [OK] Uncommented import site in ._pth file.
        )
    )
)

:: ----------------------------------------------------------------
:: Step 3: Install pip if not present
:: ----------------------------------------------------------------
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo  Installing pip...
    curl -L -o "%BASE%get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
    if errorlevel 1 (
        echo  [ERROR] Failed to download get-pip.py.
        goto :error
    )
    "%PYTHON_EXE%" "%BASE%get-pip.py" --no-warn-script-location
    del "%BASE%get-pip.py" 2>nul
    echo  [OK] pip installed.
) else (
    echo  [OK] pip already available.
)

:: ----------------------------------------------------------------
:: Step 4: Install dependencies
:: ----------------------------------------------------------------
echo  Installing dependencies (Pillow, imagehash)...
"%PYTHON_EXE%" -m pip install --no-warn-script-location -r "%BASE%requirements.txt" >nul 2>&1
if errorlevel 1 (
    echo  [WARNING] pip install had issues. Trying individually...
    "%PYTHON_EXE%" -m pip install --no-warn-script-location Pillow
    "%PYTHON_EXE%" -m pip install --no-warn-script-location imagehash
)
echo  [OK] Dependencies installed.

:: ----------------------------------------------------------------
:: Step 5: Generate launch.vbs
:: ----------------------------------------------------------------
echo  Generating launchers...

(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo Set fso = CreateObject^("Scripting.FileSystemObject"^)
echo baseDir = fso.GetParentFolderName^(WScript.ScriptFullName^)
echo WshShell.CurrentDirectory = baseDir
echo WshShell.Run """" ^& baseDir ^& "\python\python.exe"" """ ^& baseDir ^& "\dupefinder_app.py""", 0, False
echo WScript.Sleep 2000
echo WshShell.Run "http://127.0.0.1:8787", 1, False
) > "%BASE%launch.vbs"

echo  [OK] launch.vbs created.

:: ----------------------------------------------------------------
:: Step 6: Generate launch.bat
:: ----------------------------------------------------------------
(
echo @echo off
echo cd /d "%%~dp0"
echo echo Starting DupeFinder...
echo echo.
echo "%%~dp0python\python.exe" dupefinder_app.py
echo echo.
echo echo DupeFinder has stopped. Press any key to close.
echo pause ^>nul
) > "%BASE%launch.bat"

echo  [OK] launch.bat created.

:: ----------------------------------------------------------------
:: Step 7: Offer to create desktop shortcut
:: ----------------------------------------------------------------
echo.
set /p SHORTCUT="  Create a desktop shortcut? [Y/N]: "
if /i "%SHORTCUT%"=="Y" (
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine($ws.SpecialFolders('Desktop'), 'DupeFinder.lnk')); $s.TargetPath = '%BASE%launch.vbs'; $s.WorkingDirectory = '%BASE%'; $s.Description = 'DupeFinder - Find and clean duplicate images'; $s.Save()"
    if errorlevel 1 (
        echo  [WARNING] Could not create shortcut. You can create one manually.
    ) else (
        echo  [OK] Desktop shortcut created.
    )
)

:: ----------------------------------------------------------------
:: Step 8: Write setup info
:: ----------------------------------------------------------------
(
echo {
echo   "python_version": "%PYTHON_VERSION%",
echo   "python_path": "python\\python.exe",
echo   "setup_date": "%date% %time%"
echo }
) > "%BASE%setup_info.json"

:: ----------------------------------------------------------------
:: Done
:: ----------------------------------------------------------------
echo.
echo  ========================================
echo  Setup complete!
echo  ========================================
echo.
echo  To start DupeFinder:
echo    - Double-click the DupeFinder shortcut on your desktop
echo    - Or double-click launch.vbs in this folder
echo    - Or run launch.bat for debug mode
echo.
echo  To uninstall:
echo    - Shut down the server from the browser
echo    - Delete this folder
echo    - Delete the desktop shortcut if created
echo.
echo  Note: If Windows Defender blocks file operations,
echo  you may need to whitelist Python in Controlled Folder Access:
echo    Windows Security ^> Virus ^& threat protection ^> Ransomware protection
echo    ^> Allow an app ^> Add: %PYTHON_EXE%
echo.
pause
exit /b 0

:error
echo.
echo  Setup failed. See errors above.
pause
exit /b 1
