#Requires -Version 5.1
<#
.SYNOPSIS
  実行に必要な Python ファイルだけを Dest へコピーする。
  全コピー後の削除ではなく、除外リスト付きで最初から最小コピーする。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Dest,

    [switch]$IncludePip
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "  $Message"
}

function Ensure-EmptyDir([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Invoke-RoboCopyFiltered {
    param(
        [string]$From,
        [string]$To,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )

    if (-not (Test-Path -LiteralPath $From)) {
        return
    }

    New-Item -ItemType Directory -Path $To -Force | Out-Null

    $args = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/R:1", "/W:1")
    if ($ExcludeDirs.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFiles
    }

    & robocopy @args | Out-Null
    # robocopy: 0-7 は成功扱い
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy に失敗しました ($LASTEXITCODE): $From -> $To"
    }
    # 呼び出し元の exit code に影響しないようリセット
    $global:LASTEXITCODE = 0
}

function Copy-RootRuntimeFiles([string]$From, [string]$To) {
    $patterns = @(
        "python.exe",
        "pythonw.exe",
        "python3.dll",
        "python3??.dll",
        "vcruntime*.dll",
        "LICENSE.txt"
    )
    foreach ($pattern in $patterns) {
        Get-ChildItem -LiteralPath $From -File -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination $To -Force
                Write-Step ("root: " + $_.Name)
            }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $To "python.exe"))) {
        throw "python.exe をコピーできませんでした: $From"
    }
}

function Copy-PipFromSource([string]$From, [string]$To) {
    $srcSite = Join-Path $From "Lib\site-packages"
    $dstSite = Join-Path $To "Lib\site-packages"
    New-Item -ItemType Directory -Path $dstSite -Force | Out-Null

    if (-not (Test-Path -LiteralPath $srcSite)) {
        return
    }

    $pipNames = @("pip", "setuptools", "wheel", "pkg_resources", "_distutils_hack")
    Get-ChildItem -LiteralPath $srcSite -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $name = $_.Name
        $isPipRelated = $false
        foreach ($prefix in $pipNames) {
            if ($name -eq $prefix -or $name -like ($prefix + "-*") -or $name -eq "distutils-precedence.pth") {
                $isPipRelated = $true
                break
            }
        }
        if (-not $isPipRelated) { return }

        $target = Join-Path $dstSite $name
        if ($_.PSIsContainer) {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
        Write-Step ("pip: " + $name)
    }

    $srcScripts = Join-Path $From "Scripts"
    $dstScripts = Join-Path $To "Scripts"
    if (Test-Path -LiteralPath $srcScripts) {
        New-Item -ItemType Directory -Path $dstScripts -Force | Out-Null
        Get-ChildItem -LiteralPath $srcScripts -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^(pip|pip3)(\.exe|\-script\.py|\.py)?$' -or $_.Name -match '^pip3\.\d+(\.exe)?$' } |
            ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dstScripts $_.Name) -Force
                Write-Step ("script: " + $_.Name)
            }
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $Source "python.exe"))) {
    throw "コピー元に python.exe がありません: $Source"
}

Write-Host "[Copy-MinimalPython] Source=$Source"
Write-Host "[Copy-MinimalPython] Dest=$Dest"
Ensure-EmptyDir -Path $Dest

Copy-RootRuntimeFiles -From $Source -To $Dest

# 拡張モジュール（_tkinter 等）。デバッグ記号・リンク用は除外
$dllsSrc = Join-Path $Source "DLLs"
$dllsDst = Join-Path $Dest "DLLs"
if (Test-Path -LiteralPath $dllsSrc) {
    Write-Step "DLLs/ をコピー（*.pdb / *.lib 除外）"
    Invoke-RoboCopyFiltered -From $dllsSrc -To $dllsDst `
        -ExcludeFiles @("*.pdb", "*.lib", "*.exp", "*.a")
}

# 標準ライブラリ（開発・テスト・巨大ドキュメント系は最初から除外）
$libSrc = Join-Path $Source "Lib"
$libDst = Join-Path $Dest "Lib"
$libExclude = @(
    "test",
    "tests",
    "idlelib",
    "turtledemo",
    "ensurepip",
    "pydoc_data",
    "lib2to3",
    "site-packages",
    "venv",
    "curses",
    "__pycache__"
)
Write-Step "Lib/ を必要分だけコピー（site-packages / test 等は除外）"
Invoke-RoboCopyFiltered -From $libSrc -To $libDst `
    -ExcludeDirs $libExclude `
    -ExcludeFiles @("*.pyc", "*.pyo")

# site-packages は空で開始（依存は後で pip インストール）
New-Item -ItemType Directory -Path (Join-Path $Dest "Lib\site-packages") -Force | Out-Null

# tkinter 用 Tcl/Tk（デモ・ビルド用を除外）
$tclSrc = Join-Path $Source "tcl"
$tclDst = Join-Path $Dest "tcl"
if (Test-Path -LiteralPath $tclSrc) {
    Write-Step "tcl/ を必要分だけコピー（demos / nmake 除外）"
    Invoke-RoboCopyFiltered -From $tclSrc -To $tclDst `
        -ExcludeDirs @("nmake", "demos", "demo", "__pycache__") `
        -ExcludeFiles @("*.pdb", "*.lib")
}

if ($IncludePip) {
    Write-Step "セットアップ用に pip だけ site-packages へコピー"
    Copy-PipFromSource -From $Source -To $Dest
}

$sizeMb = [math]::Round(((Get-ChildItem -LiteralPath $Dest -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host ("[Copy-MinimalPython] 完了: 約 {0} MB" -f $sizeMb)
exit 0
