param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765,
    [string]$Python = "",
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

if (-not $Python) {
    $CadflowPython = Join-Path $ProjectRoot ".venv-cadflow\Scripts\python.exe"
    $DefaultPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $CadflowPython) {
        $Python = $CadflowPython
    } elseif (Test-Path $DefaultPython) {
        $Python = $DefaultPython
    } else {
        $Python = "python"
    }
}

$SourcePath = Join-Path $ProjectRoot "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$SourcePath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $SourcePath
}

$Url = "http://${HostName}:${Port}/workflow-console.html"
Write-Host "CadFlow Workflow Console"
Write-Host "Project: $ProjectRoot"
Write-Host "Python:  $Python"
Write-Host "URL:     $Url"
Write-Host ""
Write-Host "Press Ctrl+C to stop the local console."

if ($Open) {
    Start-Process $Url
}

& $Python -m ai_native_cad.workflow_console.server --host $HostName --port $Port
