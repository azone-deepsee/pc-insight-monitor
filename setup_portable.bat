@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [エラー] 作業フォルダへ移動できません。
    pause
    exit /b 1
)

echo ============================================
echo  PC Insight Monitor - ポータブル Python 準備
echo  （開発PCで1回だけ実行）
echo ============================================
echo.
echo 作業フォルダ: %CD%
echo.

set PYVER=3.12.10
set PYINSTALLER=python-%PYVER%-amd64.exe
set PYURL=https://www.python.org/ftp/python/%PYVER%/%PYINSTALLER%
set PYDIR=%CD%\python
set PYTEMP=%TEMP%\%PYINSTALLER%
set SOURCE_PY=
set SETUP_METHOD=

if exist "%PYDIR%\python.exe" (
    echo [情報] 既に python フォルダがあります。再セットアップします。
    rmdir /s /q "%PYDIR%"
)

mkdir "%PYDIR%" 2>nul

REM --- 方法A: 開発PCの Python 3.12 を丸ごとコピー（推奨） ---
REM 同一PCに Python 3.12 があると、インストーラは TargetDir を無視する既知の問題があるため。
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "SOURCE_PY=%LOCALAPPDATA%\Programs\Python\Python312"
    goto :copy_python
)

for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.prefix)" 2^>nul') do (
    if exist "%%i\python.exe" set "SOURCE_PY=%%i"
)
if defined SOURCE_PY goto :copy_python

:copy_python
if defined SOURCE_PY (
    echo [1/4] 開発PCの Python 3.12 をコピーします...
    echo       コピー元: %SOURCE_PY%
    echo       コピー先: %PYDIR%
    echo.
    rmdir /s /q "%PYDIR%" 2>nul
    mkdir "%PYDIR%"
    robocopy "%SOURCE_PY%" "%PYDIR%" /E /NFL /NDL /NJH /NJS /NC /NS >nul
    if exist "%PYDIR%\python.exe" (
        set "SETUP_METHOD=copy"
        goto :install_deps
    )
    echo [警告] コピーに失敗しました。インストーラ方式を試します。
    echo.
)

REM --- 方法B: インストーラで新規配置（Python 3.12 未導入のPC向け） ---
echo [1/4] Python インストーラをダウンロード（tkinter 同梱版）...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYTEMP%'"

if errorlevel 1 (
    echo ダウンロードに失敗しました。ネットワーク接続を確認してください。
    goto :fail
)

echo [2/4] Python をポータブルフォルダへインストール...
echo       ※ 開発PCに Python 3.12 が既にある場合、この方式は失敗することがあります。
echo.

start /wait "" "%PYTEMP%" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_doc=0 Include_launcher=0 Include_pip=1 Include_tcltk=1 TargetDir="%PYDIR%"

if not exist "%PYDIR%\python.exe" (
    echo [エラー] Python のインストールに失敗しました。
    echo.
    echo よくある原因:
    echo   開発PCに Python 3.12 が既にインストールされている
    echo   ^(この場合、インストーラが TargetDir を無視します^)
    echo.
    echo 対処:
    echo   1. https://www.python.org/downloads/ から Python 3.12 をインストール
    echo   2. この setup_portable.bat を再実行 ^(自動でコピー方式に切り替わります^)
    echo.
    goto :fail
)
set "SETUP_METHOD=installer"

:install_deps
echo [3/4] 依存パッケージをインストール...
"%PYDIR%\python.exe" -m pip install --no-warn-script-location -r "%CD%\requirements.txt"
if errorlevel 1 (
    echo 依存パッケージのインストールに失敗しました。
    goto :fail
)

if exist "%PYDIR%\Scripts\pywin32_postinstall.py" (
    "%PYDIR%\python.exe" "%PYDIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

echo [4/4] 動作確認...
"%PYDIR%\python.exe" -c "import tkinter; import win32evtlog; import psutil; print('All OK')"
if errorlevel 1 (
    echo 動作確認に失敗しました。diagnose.bat で詳細を確認してください。
    goto :fail
)

del "%PYTEMP%" >nul 2>&1

echo.
echo 完了しました。方式: %SETUP_METHOD%
echo このフォルダ一式をファイルサーバへ配置してください。
echo 現場PCでは run.bat を実行してください。
echo 起動できない場合は diagnose.bat を実行してください。
echo.
popd 2>nul
pause
exit /b 0

:fail
popd 2>nul
pause
exit /b 1
