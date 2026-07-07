@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYEXE=%~dp0python\python.exe"

if exist "%PYEXE%" (
    goto :run
)

where python >nul 2>&1
if not errorlevel 1 (
    echo [情報] ポータブル Python がありません。システムの Python で起動します。
    echo         ファイルサーバ配布前に setup_portable.bat を実行してください。
    set "PYEXE=python"
    goto :run
)

echo Python が見つかりません。
echo.
echo ファイルサーバ配布用:
echo   開発PCで setup_portable.bat を1回実行してから配置してください。
echo.
pause
exit /b 1

:run
"%PYEXE%" -c "import win32evtlog" >nul 2>&1
if errorlevel 1 (
    if /i "%PYEXE%"=="python" (
        echo 依存パッケージをインストールします...
        python -m pip install -r requirements.txt
    ) else (
        echo ポータブル Python のセットアップが不完全です。
        echo setup_portable.bat を再実行してください。
        pause
        exit /b 1
    )
)

"%PYEXE%" run.py
if errorlevel 1 pause
