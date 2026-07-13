@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "SOURCE=%~dp0"
if "%SOURCE:~-1%"=="\" set "SOURCE=%SOURCE:~0,-1%"

set "LOCAL_APP=%LOCALAPPDATA%\PCInsightMonitor\app"
set "ROOT=%SOURCE%"
set "SYNCED=0"

rem 既にローカルキャッシュから起動している場合は同期をスキップ
echo %SOURCE% | findstr /I /C:"%LOCALAPPDATA%\PCInsightMonitor\app" >nul
if not errorlevel 1 goto :resolve_python

rem ネットワーク共有、またはポータブル配布時はローカルへ同期
if /i not "%SOURCE%"=="%LOCAL_APP%" (
    if exist "%SOURCE%\python\python.exe" set "SYNCED=1"
)
echo %SOURCE% | findstr /B "\\\\" >nul && set "SYNCED=1"

if "%SYNCED%"=="1" (
    echo [情報] ローカルへ同期しています...
    if not exist "%LOCAL_APP%" mkdir "%LOCAL_APP%"
    robocopy "%SOURCE%" "%LOCAL_APP%" /E /XD __pycache__ .git logs /XF *.pyc /R:2 /W:2 /NFL /NDL /NJH /NJS /NC /NS
    if errorlevel 8 (
        echo [エラー] ローカル同期に失敗しました。
        echo パス: %SOURCE%
        pause
        exit /b 1
    )
    set "ROOT=%LOCAL_APP%"
    echo [情報] ローカルから起動します: %ROOT%
    echo.
)

:resolve_python
pushd "%ROOT%" 2>nul
if errorlevel 1 (
    echo [エラー] フォルダへ移動できません: %ROOT%
    pause
    exit /b 1
)

set "PYEXE=%ROOT%\python\python.exe"

if exist "%PYEXE%" goto :check_deps

where python >nul 2>&1
if not errorlevel 1 (
    echo [情報] ポータブル Python がありません。システムの Python で起動します。
    set "PYEXE=python"
    goto :check_deps
)

echo Python が見つかりません。
echo setup_portable.bat を実行してから配布してください。
popd 2>nul
pause
exit /b 1

:check_deps
"%PYEXE%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [エラー] tkinter が利用できません。
    popd 2>nul
    pause
    exit /b 1
)

"%PYEXE%" -c "import win32evtlog" >nul 2>&1
if errorlevel 1 (
    if /i "%PYEXE%"=="python" (
        python -m pip install -r "%ROOT%\requirements.txt"
    ) else (
        echo [エラー] ポータブル Python のセットアップが不完全です。
        popd 2>nul
        pause
        exit /b 1
    )
)

"%PYEXE%" "%ROOT%\run.py"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo [エラー] アプリが終了しました（コード %EXITCODE%）
    pause
)

popd 2>nul
exit /b %EXITCODE%
