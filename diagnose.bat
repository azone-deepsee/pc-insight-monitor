@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

pushd "%~dp0" 2>nul
if errorlevel 1 (
    echo [エラー] 作業フォルダへ移動できません: %~dp0
    goto :end
)

echo ============================================
echo  PC Insight Monitor - 環境診断
echo ============================================
echo.
echo 作業フォルダ: %CD%
echo.

set "FAIL=0"
set "PYEXE=%~dp0python\python.exe"

if exist "%PYEXE%" (
    echo [OK] ポータブル Python: %PYEXE%
) else (
    echo [NG] ポータブル Python がありません
    echo      開発PCで setup_portable.bat を実行してから配布してください
    set "FAIL=1"
    where python >nul 2>&1
    if not errorlevel 1 (
        echo [情報] システム Python は見つかりました（配布用には不十分な場合があります）
        set "PYEXE=python"
    ) else (
        echo [NG] システム Python も見つかりません
        goto :end
    )
)

echo.
echo --- Python モジュール確認 ---
for %%m in (tkinter win32evtlog psutil) do (
    "%PYEXE%" -c "import %%m" >nul 2>&1
    if errorlevel 1 (
        echo [NG] import %%m
        set "FAIL=1"
    ) else (
        echo [OK] import %%m
    )
)

echo.
echo --- tkinter ウィンドウテスト ---
"%PYEXE%" -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy(); print('tkinter window OK')" 2>&1
if errorlevel 1 (
    echo [NG] tkinter が動作しません（GUI起動不可）
    set "FAIL=1"
)

echo.
echo --- WMI 確認（USB/COM監視）---
"%PYEXE%" -c "import pythoncom,win32com.client; pythoncom.CoInitialize(); w=win32com.client.GetObject('winmgmts:'); list(w.ExecQuery('SELECT Caption FROM Win32_PnPEntity WHERE PNPClass=''Ports''')); print('WMI OK')" 2>&1
if errorlevel 1 (
    echo [NG] WMI / Win32_PnPEntity
    set "FAIL=1"
) else (
    echo [OK] WMI / Win32_PnPEntity
)

echo.
echo --- ログ書き込み確認 ---
"%PYEXE%" -c "import os; from pathlib import Path; p=Path(os.environ.get('LOCALAPPDATA','.'))/'PCInsightMonitor'/'logs'; p.mkdir(parents=True, exist_ok=True); t=p/'_diagnose_test.txt'; t.write_text('ok', encoding='utf-8'); t.unlink(); print('LOCALAPPDATA write OK')" 2>&1
if errorlevel 1 (
    echo [NG] %%LOCALAPPDATA%% への書き込みに失敗しました
    set "FAIL=1"
)

echo.
if "%FAIL%"=="0" (
    echo ============================================
    echo  診断結果: 問題は検出されませんでした
    echo  run.bat で起動できるはずです
    echo ============================================
) else (
    echo ============================================
    echo  診断結果: 問題があります
    echo  開発PCで setup_portable.bat を再実行し、
    echo  python フォルダごとファイルサーバへ再配置してください
    echo ============================================
)

:end
popd 2>nul
echo.
pause
