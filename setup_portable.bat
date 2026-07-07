@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ============================================
echo  PC Insight Monitor - ポータブル Python 準備
echo  （開発PCで1回だけ実行）
echo ============================================
echo.

set PYVER=3.12.10
set PYZIP=python-%PYVER%-embed-amd64.zip
set PYURL=https://www.python.org/ftp/python/%PYVER%/%PYZIP%
set PYDIR=%~dp0python

if exist "%PYDIR%\python.exe" (
    echo [情報] 既に python フォルダがあります。再セットアップします。
    rmdir /s /q "%PYDIR%"
)

mkdir "%PYDIR%"

echo [1/5] Python 埋め込み版をダウンロード...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYURL%' -OutFile $env:TEMP'\%PYZIP%'"

if errorlevel 1 (
    echo ダウンロードに失敗しました。ネットワーク接続を確認してください。
    pause
    exit /b 1
)

echo [2/5] 展開...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Expand-Archive -Path $env:TEMP'\%PYZIP%' -DestinationPath '%PYDIR%' -Force"

echo [3/5] pip を有効化...
for %%f in ("%PYDIR%\python*._pth") do (
    copy /y "%%f" "%%f.bak" >nul
    (
        echo python312.zip
        echo .
        echo Lib\site-packages
        echo import site
    ) > "%%f"
)

echo [4/5] pip をインストール...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%PYDIR%\get-pip.py'"

"%PYDIR%\python.exe" "%PYDIR%\get-pip.py" --no-warn-script-location
if errorlevel 1 (
    echo pip のインストールに失敗しました。
    pause
    exit /b 1
)

echo [5/5] 依存パッケージをインストール...
"%PYDIR%\python.exe" -m pip install --no-warn-script-location -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo 依存パッケージのインストールに失敗しました。
    pause
    exit /b 1
)

if exist "%PYDIR%\Scripts\pywin32_postinstall.py" (
    "%PYDIR%\python.exe" "%PYDIR%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
)

"%PYDIR%\python.exe" -c "import win32evtlog; print('pywin32 OK')"
if errorlevel 1 (
    echo pywin32 の動作確認に失敗しました。
    pause
    exit /b 1
)

del "%PYDIR%\get-pip.py" >nul 2>&1

echo.
echo 完了しました。
echo このフォルダ一式をファイルサーバへ配置し、現場PCでは run.bat を実行してください。
echo.
pause
