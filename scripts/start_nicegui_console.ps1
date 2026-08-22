param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8780,
    [string]$Python = "",
    [switch]$Open,
    [switch]$ForcePortCleanup
)

$ErrorActionPreference = "Stop"

function Get-ListeningProcessIds {
    param([int]$TargetPort)

    $listenerIds = @()
    try {
        $listenerIds = @(
            Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess
        )
    } catch {
        # Get-NetTCPConnection can require elevated access on some Windows
        # installations. netstat is a read-only fallback available to normal
        # desktop users.
        $netstatPath = Join-Path $env:SystemRoot "System32\netstat.exe"
        if (Test-Path $netstatPath) {
            $pattern = "^\s*TCP\s+\S+:$TargetPort\s+\S+\s+LISTENING\s+(\d+)\s*$"
            $listenerIds = @(
                & $netstatPath -ano -p tcp 2>$null |
                    ForEach-Object {
                        if ($_ -match $pattern) {
                            [int]$Matches[1]
                        }
                    }
            )
        }
    }
    return @($listenerIds | Where-Object { $_ -gt 0 } | Sort-Object -Unique)
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)

    try {
        return (
            Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        ).CommandLine
    } catch {
        return $null
    }
}

function Test-CadFlowNiceGuiProcess {
    param(
        [string]$CommandLine,
        [int]$TargetPort
    )

    if (-not $CommandLine) {
        return $false
    }
    $modulePattern = [regex]::Escape("ai_native_cad.workflow_console.nicegui_app")
    $portPattern = "(?:--port(?:=|\s+))$TargetPort(?:\s|$)"
    return $CommandLine -match $modulePattern -and $CommandLine -match $portPattern
}

function Test-CadFlowNiceGuiEndpoint {
    param(
        [string]$ProbeHost,
        [int]$TargetPort
    )

    if ($ProbeHost -eq "0.0.0.0") {
        $ProbeHost = "127.0.0.1"
    } elseif ($ProbeHost -eq "::" -or $ProbeHost -eq "[::]") {
        $ProbeHost = "[::1]"
    }

    $previousProgressPreference = $ProgressPreference
    try {
        $ProgressPreference = "SilentlyContinue"
        $response = Invoke-WebRequest `
            -Uri "http://${ProbeHost}:${TargetPort}/" `
            -UseBasicParsing `
            -TimeoutSec 2 `
            -ErrorAction Stop
        return $response.Content -match '<title>\s*CadFlow Workflow Console\s*</title>'
    } catch {
        return $false
    } finally {
        $ProgressPreference = $previousProgressPreference
    }
}

function Stop-ExistingListener {
    param(
        [int]$TargetPort,
        [string]$ProbeHost,
        [switch]$Force
    )

    $listenerIds = @(Get-ListeningProcessIds -TargetPort $TargetPort)
    foreach ($listenerProcessId in $listenerIds) {
        $listenerProcess = Get-Process -Id $listenerProcessId -ErrorAction SilentlyContinue
        if (-not $listenerProcess) {
            continue
        }
        $commandLine = Get-ProcessCommandLine -ProcessId $listenerProcessId
        $isCadFlow = Test-CadFlowNiceGuiProcess -CommandLine $commandLine -TargetPort $TargetPort
        if (-not $isCadFlow -and $listenerIds.Count -eq 1) {
            # Some locked-down Windows sessions deny Win32_Process command-line
            # access. The app's exact page title is a safe secondary identity
            # check before terminating the listener.
            $isCadFlow = Test-CadFlowNiceGuiEndpoint -ProbeHost $ProbeHost -TargetPort $TargetPort
        }
        if (-not $isCadFlow -and -not $Force) {
            $processName = $listenerProcess.ProcessName
            throw (
                "Port $TargetPort is occupied by non-CadFlow process " +
                "$listenerProcessId ($processName). Stop it manually or rerun " +
                "with -ForcePortCleanup if terminating it is intentional."
            )
        }
        if ($isCadFlow) {
            Write-Host "Stopping previous CadFlow NiceGUI process $listenerProcessId on port $TargetPort..."
        } else {
            Write-Warning "Force-stopping process $listenerProcessId on port $TargetPort."
        }
        Stop-Process -Id $listenerProcessId -Force -ErrorAction Stop
    }

    if ($listenerIds.Count -gt 0) {
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (@(Get-ListeningProcessIds -TargetPort $TargetPort).Count -eq 0) {
                return
            }
            Start-Sleep -Milliseconds 250
        }
        throw "Port $TargetPort did not become available after cleanup."
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Port must be between 1 and 65535."
}

if (-not $Python) {
    $CadflowPython = Join-Path $ProjectRoot ".venv-cadflow\Scripts\python.exe"
    if (Test-Path $CadflowPython) {
        $Python = $CadflowPython
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

$Url = "http://${HostName}:${Port}/"
Stop-ExistingListener -TargetPort $Port -ProbeHost $HostName -Force:$ForcePortCleanup

Write-Host "CadFlow NiceGUI Workflow Console"
Write-Host "Project: $ProjectRoot"
Write-Host "Python:  $Python"
Write-Host "URL:     $Url"
Write-Host ""
Write-Host "Press Ctrl+C to stop the local console."

if ($Open) {
    Start-Process $Url
}

& $Python -m ai_native_cad.workflow_console.nicegui_app --host $HostName --port $Port
