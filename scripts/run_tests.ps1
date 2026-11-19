<#
.SYNOPSIS
    执行 UI 自动化测试并生成 Allure 报告。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
    powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 -Markers smoke -Headed
    powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1 -Workers 4 -OpenReport
#>
param(
    [string]$Env = "test",
    [string]$Markers = "",
    [switch]$Headed,
    [int]$Workers = 0,
    [switch]$OpenReport
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "未找到虚拟环境 $Python，请先创建 .venv 并安装 requirements.txt"
}

$PytestArgs = @("-m", "pytest", "--env=$Env")
if ($Markers) { $PytestArgs += @("-m", $Markers) }
if ($Headed) { $PytestArgs += "--headed" }
if ($Workers -gt 0) { $PytestArgs += @("-n", "$Workers") }

Push-Location $Root
& $Python @PytestArgs
$ExitCode = $LASTEXITCODE

$AllureDir = Get-ChildItem (Join-Path $Root "tools") -Directory -Filter "allure-*" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($AllureDir) {
    $Jre = Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Directory -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $env:JAVA_HOME -and $Jre) { $env:JAVA_HOME = $Jre.FullName }

    $AllureBat = Join-Path $AllureDir.FullName "bin\allure.bat"
    $Results = Join-Path $Root "reports\allure-results"
    $Report = Join-Path $Root "reports\allure-report"
    if (Test-Path $AllureBat) {
        & $AllureBat generate $Results -o $Report --clean
        if ($OpenReport) { Start-Process (Join-Path $Report "index.html") }
    }
}
$ExecutionReport = Join-Path $Root "reports\execution-report.html"
if (Test-Path $ExecutionReport) { Write-Host "测试报告（含执行过程）: $ExecutionReport" }
Pop-Location
exit $ExitCode
