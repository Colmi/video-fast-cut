[CmdletBinding()]
param(
    [switch]$KeepBuild
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Source = Join-Path $Root "src\VideoCutAssistant.pyw"
$Icon = Join-Path $Root "assets\logo.ico"
$Vendor = Join-Path $Root "vendor"
$Release = Join-Path $Root "release"
$Build = Join-Path $Root "build"

$OriginalLocation = Get-Location
$BuildSucceeded = $false
try {
    Set-Location $Root
    New-Item -ItemType Directory -Path $Release, $Build -Force | Out-Null

    & python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "未安装 PyInstaller。请先运行：python -m pip install -r requirements-dev.txt"
    }

    & python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name "VideoCutAssistant" `
        --icon $Icon `
        --paths $Vendor `
        --hidden-import "tkinterdnd2" `
        --add-data "$Icon;assets" `
        --distpath $Release `
        --workpath (Join-Path $Build "pyinstaller") `
        --specpath $Build `
        $Source

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出代码：$LASTEXITCODE"
    }
    $BuildSucceeded = $true
    Write-Host ""
    Write-Host "构建完成：$Release\VideoCutAssistant.exe" -ForegroundColor Green
}
finally {
    Set-Location $OriginalLocation
    if ($BuildSucceeded -and -not $KeepBuild -and (Test-Path $Build)) {
        Remove-Item -LiteralPath $Build -Recurse -Force -ErrorAction SilentlyContinue
    }
}


