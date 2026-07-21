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
echo  方針: 必要最小限だけコピー（全コピー後削除はしない）
echo ============================================
echo.
echo 作業フォルダ: %CD%
echo.

set PYVER=3.12.10
set PYINSTALLER=python-%PYVER%-amd64.exe
set PYURL=https://www.python.org/ftp/python/%PYVER%/%PYINSTALLER%
set PYDIR=%CD%\python
set PYTEMP=%TEMP%\%PYINSTALLER%
set TOOLS=%CD%\tools
set SOURCE_PY=
set SETUP_METHOD=

if not exist "%TOOLS%\Copy-MinimalPython.ps1" (
    echo [エラー] tools\Copy-MinimalPython.ps1 が見つかりません。
    goto :fail
)
if not exist "%TOOLS%\Trim-PortablePython.ps1" (
    echo [エラー] tools\Trim-PortablePython.ps1 が見つかりません。
    goto :fail
)

if exist "%PYDIR%\python.exe" (
    echo [情報] 既に python フォルダがあります。再セットアップします。
    rmdir /s /q "%PYDIR%"
)

mkdir "%PYDIR%" 2>nul

rem --- コピー元 Python 3.12 を探索 ---
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "SOURCE_PY=%LOCALAPPDATA%\Programs\Python\Python312"
    goto :prepare
)

for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.prefix)" 2^>nul') do (
    if exist "%%i\python.exe" set "SOURCE_PY=%%i"
)
if defined SOURCE_PY goto :prepare

:prepare
if defined SOURCE_PY (
    echo [1/5] 開発PCの Python 3.12 から必要最小限だけコピーします...
    echo       コピー元: %SOURCE_PY%
    echo       コピー先: %PYDIR%
    echo       ※ Doc / Include / test / site-packages 等は最初から除外
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%TOOLS%\Copy-MinimalPython.ps1" -Source "%SOURCE_PY%" -Dest "%PYDIR%" -IncludePip
    if errorlevel 1 (
        echo [警告] 最小コピーに失敗しました。インストーラ方式を試します。
        echo.
        rmdir /s /q "%PYDIR%" 2>nul
        mkdir "%PYDIR%" 2>nul
        goto :installer
    )
    if not exist "%PYDIR%\python.exe" (
        echo [警告] 最小コピーに失敗しました。インストーラ方式を試します。
        echo.
        goto :installer
    )
    set "SETUP_METHOD=minimal-copy"
    goto :ensure_pip
)

:installer
echo [1/5] Python インストーラをダウンロード...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYTEMP%'"
if errorlevel 1 (
    echo ダウンロードに失敗しました。ネットワーク接続を確認してください。
    goto :fail
)

echo [2/5] Python をポータブルフォルダへ最小構成でインストール...
start /wait "" "%PYTEMP%" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_doc=0 Include_dev=0 Include_launcher=0 Include_symbols=0 Include_debug=0 Include_pip=1 Include_tcltk=1 TargetDir="%PYDIR%"

if not exist "%PYDIR%\python.exe" (
    echo [エラー] Python のインストールに失敗しました。
    echo 開発PCに Python 3.12 をインストールしてから再実行してください。
    goto :fail
)
set "SETUP_METHOD=installer-minimal"

echo       インストーラ成果物から不要分を削除...
powershell -NoProfile -ExecutionPolicy Bypass -File "%TOOLS%\Trim-PortablePython.ps1" -Dest "%PYDIR%"
goto :install_deps

:ensure_pip
echo [2/5] pip の利用可否を確認...
"%PYDIR%\python.exe" -m pip --version >nul 2>&1
if not errorlevel 1 goto :install_deps

echo       ソースに pip が無いため get-pip.py で導入します...
set GETPIP=%TEMP%\get-pip-pcinsight.py
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GETPIP%'"
if errorlevel 1 (
    echo get-pip.py のダウンロードに失敗しました。
    goto :fail
)
"%PYDIR%\python.exe" "%GETPIP%" --no-warn-script-location
if errorlevel 1 (
    echo pip の導入に失敗しました。
    goto :fail
)
del "%GETPIP%" >nul 2>&1

:install_deps
echo [3/5] 依存パッケージをインストール...
"%PYDIR%\python.exe" -m pip install --no-warn-script-location --disable-pip-version-check -r "%CD%\requirements.txt"
if errorlevel 1 (
    echo 依存パッケージのインストールに失敗しました。
    goto :fail
)

if exist "%PYDIR%\Scripts\pywin32_postinstall.py" (
    "%PYDIR%\python.exe" "%PYDIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

echo [4/5] 実行に不要な pip / キャッシュを削除して最終軽量化...
powershell -NoProfile -ExecutionPolicy Bypass -File "%TOOLS%\Trim-PortablePython.ps1" -Dest "%PYDIR%" -RemovePip -Aggressive

echo [5/5] 動作確認...
"%PYDIR%\python.exe" -c "import tkinter; import win32evtlog; import psutil; import win32com.client; print('All OK')"
if errorlevel 1 (
    echo 動作確認に失敗しました。diagnose.bat で詳細を確認してください。
    goto :fail
)

for /f "delims=" %%s in ('powershell -NoProfile -Command "(Get-ChildItem -LiteralPath '%PYDIR%' -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB"') do (
    set "FINAL_SIZE=%%s"
)

del "%PYTEMP%" >nul 2>&1

echo.
echo 完了しました。
echo   方式: %SETUP_METHOD%
echo   python フォルダサイズ: 約 %FINAL_SIZE% MB
echo.
echo このフォルダ一式をファイルサーバへ配置してください。
echo 現場PCでは run.bat を実行してください。
echo.
popd 2>nul
pause
exit /b 0

:fail
popd 2>nul
pause
exit /b 1
