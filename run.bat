@echo off
chcp 65001 >nul
setlocal

rem UNCパス（ファイルサーバ）対応: pushd で一時ドライブにマップ
pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [エラー] フォルダへ移動できません。
    echo パス: %~dp0
    echo ネットワーク共有の場合はアクセス権を確認するか、ローカルにコピーして試してください。
    pause
    exit /b 1
)

set "ROOT=%CD%"
set "PYEXE=%ROOT%\python\python.exe"

if exist "%PYEXE%" (
    goto :check_deps
)

where python >nul 2>&1
if not errorlevel 1 (
    echo [情報] ポータブル Python がありません。システムの Python で起動します。
    echo         ファイルサーバ配布前に setup_portable.bat を実行してください。
    set "PYEXE=python"
    goto :check_deps
)

echo Python が見つかりません。
echo.
echo 対処:
echo   1. 開発PCで setup_portable.bat を1回実行
echo   2. python フォルダを含めてファイルサーバへ再配置
echo   3. 問題が続く場合は diagnose.bat を実行
echo.
popd 2>nul
pause
exit /b 1

:check_deps
"%PYEXE%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [エラー] tkinter が利用できません。GUIを起動できません。
    echo setup_portable.bat を再実行して tkinter 付き Python を準備してください。
    echo 詳細は diagnose.bat を実行してください。
    popd 2>nul
    pause
    exit /b 1
)

"%PYEXE%" -c "import win32evtlog" >nul 2>&1
if errorlevel 1 (
    if /i "%PYEXE%"=="python" (
        echo 依存パッケージをインストールします...
        python -m pip install -r "%ROOT%\requirements.txt"
    ) else (
        echo [エラー] ポータブル Python のセットアップが不完全です。
        echo setup_portable.bat を再実行してください。
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
    echo diagnose.bat で環境を確認してください。
    pause
)

popd 2>nul
exit /b %EXITCODE%
