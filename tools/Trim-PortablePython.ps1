#Requires -Version 5.1
<#
.SYNOPSIS
  ポータブル Python から実行に不要なファイルを削除する。
  依存インストール後に pip / キャッシュ / テスト類を落とす用途。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Dest,

    [switch]$RemovePip,
    [switch]$Aggressive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Remove-Tree([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  removed: $Path"
    }
}

function Remove-MatchingDirs([string]$Root, [string[]]$Names) {
    if (-not (Test-Path -LiteralPath $Root)) { return }
    Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $Names -contains $_.Name } |
        Sort-Object { $_.FullName.Length } -Descending |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

if (-not (Test-Path -LiteralPath (Join-Path $Dest "python.exe"))) {
    throw "python.exe がありません: $Dest"
}

Write-Host "[Trim-PortablePython] Dest=$Dest"

# インストーラ方式で入る開発用ディレクトリ
@(
    "Doc",
    "include",
    "Include",
    "libs",
    "Libs",
    "Tools",
    "share",
    "tcl\nmake"
) | ForEach-Object { Remove-Tree (Join-Path $Dest $_) }

# 標準ライブラリの不要ツリー
@(
    "Lib\test",
    "Lib\idlelib",
    "Lib\turtledemo",
    "Lib\ensurepip",
    "Lib\pydoc_data",
    "Lib\lib2to3",
    "Lib\venv",
    "Lib\curses"
) | ForEach-Object { Remove-Tree (Join-Path $Dest $_) }

# Tcl/Tk デモ
Remove-MatchingDirs -Root (Join-Path $Dest "tcl") -Names @("demos", "demo", "nmake")

# サイトパッケージ内のテスト・キャッシュ
Remove-MatchingDirs -Root (Join-Path $Dest "Lib\site-packages") -Names @(
    "test", "tests", "testing", "__pycache__", "idle_test"
)

# ビルド成果物・デバッグ記号・バイトコード
$junkExt = @(".pdb", ".lib", ".exp", ".pyc", ".pyo", ".a")
Get-ChildItem -LiteralPath $Dest -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $junkExt -contains $_.Extension } |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
    }

Get-ChildItem -LiteralPath $Dest -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }

if ($RemovePip) {
    $site = Join-Path $Dest "Lib\site-packages"
    if (Test-Path -LiteralPath $site) {
        Get-ChildItem -LiteralPath $site -Force -ErrorAction SilentlyContinue | ForEach-Object {
            $n = $_.Name
            if (
                $n -eq "pip" -or $n -like "pip-*" -or
                $n -eq "setuptools" -or $n -like "setuptools-*" -or
                $n -eq "wheel" -or $n -like "wheel-*" -or
                $n -eq "pkg_resources" -or $n -like "pkg_resources-*" -or
                $n -eq "_distutils_hack" -or $n -eq "distutils-precedence.pth"
            ) {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  removed pip-related: $n"
            }
        }
    }
    Remove-Tree (Join-Path $Dest "Scripts")
}

if ($Aggressive) {
    # pywin32 の docs / デモ / テストがあれば削除
    @(
        "Lib\site-packages\PyWin32.chm",
        "Lib\site-packages\win32com\HTML",
        "Lib\site-packages\win32com\test",
        "Lib\site-packages\win32\test",
        "Lib\site-packages\isapi\doc",
        "Lib\site-packages\pythonwin\pywin\Demos"
    ) | ForEach-Object { Remove-Tree (Join-Path $Dest $_) }
}

$sizeMb = [math]::Round(((Get-ChildItem -LiteralPath $Dest -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host ("[Trim-PortablePython] 完了: 約 {0} MB" -f $sizeMb)
exit 0
