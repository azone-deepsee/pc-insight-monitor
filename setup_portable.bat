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

set PYVER=3.12.10
set PYINSTALLER=python-%PYVER%-amd64.exe
set PYURL=https://www.python.org/ftp/python/%PYVER%/%PYINSTALLER%
set PYDIR=%CD%\python
set PYTEMP=%TEMP%\%PYINSTALLER%

if exist "%PYDIR%\python.exe" (
    echo [情報] 既に python フォルダがあります。再セットアップします。
    rmdir /s /q "%PYDIR%"
)

mkdir "%PYDIR%"

echo [1/4] Python インストーラをダウンロード（tkinter 同梱版）...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYTEMP%'"

if errorlevel 1 (
    echo ダウンロードに失敗しました。ネットワーク接続を確認してください。
    popd 2>nul
    pause
    exit /b 1
)

echo [2/4] Python をポータブルフォルダへインストール...
"%PYTEMP%" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_doc=0 Include_launcher=0 Include_pip=1 Include_tcltk=1 TargetDir="%PYDIR%"

if not exist "%PYDIR%\python.exe" (
    echo Python のインストールに失敗しました。
    popd 2>nul
    pause
    exit /b 1
)

echo [3/4] 依存パッケージをインストール...
"%PYDIR%\python.exe" -m pip install --no-warn-script-location -r "%CD%\requirements.txt"
if errorlevel 1 (
    echo 依存パッケージのインストールに失敗しました。
    popd 2>nul
    pause
    exit /b 1
)

if exist "%PYDIR%\Scripts\pywin32_postinstall.py" (
    "%PYDIR%\python.exe" "%PYDIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

echo [4/4] 動作確認...
"%PYDIR%\python.exe" -c "import tkinter; import win32evtlog; import psutil; print('All OK')"
if errorlevel 1 (
    echo 動作確認に失敗しました。diagnose.bat で詳細を確認してください。
    popd 2>nul
    pause
    exit /b 1
)

del "%PYTEMP%" >nul 2>&1

echo.
echo 完了しました。
echo このフォルダ一式（python フォルダ含む）をファイルサーバへ配置し、
echo 現場PCでは run.bat を実行してください。
echo 起動できない場合は diagnose.bat を実行してください。
echo.
popd 2>nul
pause
