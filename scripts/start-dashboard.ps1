$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "tmp\launcher"
$apiOutLog = Join-Path $logDir "dashboard-api.out.log"
$apiErrLog = Join-Path $logDir "dashboard-api.err.log"
$webOutLog = Join-Path $logDir "dashboard-web.out.log"
$webErrLog = Join-Path $logDir "dashboard-web.err.log"
$apiUrl = "http://127.0.0.1:8000/api/health"
$webUrl = "http://127.0.0.1:5173/"
$pythonPathValue = Join-Path $repoRoot "apps\orchestrator\src"

function Resolve-PythonExecutable {
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand -and $pythonCommand.Path) {
        return $pythonCommand.Path
    }

    throw "Missing Python interpreter. Expected .venv\Scripts\python.exe or python on PATH."
}

function Show-LauncherError {
    param([string]$Message)

    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "$Message`nLogs: $logDir",
        "YouTube Story Automation",
        "OK",
        "Error"
    ) | Out-Null
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Test-TcpPortInUse {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $false
    } catch {
        return $true
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $pythonExe = Resolve-PythonExecutable

    if (-not (Test-Path (Join-Path $repoRoot "node_modules"))) {
        throw "Missing node_modules. Run npm.cmd install first."
    }

    $dashboardApiCommand = @"
`$env:PYTHONPATH = '$pythonPathValue'
& '$pythonExe' -m app dashboard-api --host 127.0.0.1 --port 8000
"@

    if (Test-TcpPortInUse -Port 8000) {
        if (-not (Wait-HttpReady -Url $apiUrl -TimeoutSeconds 5)) {
            throw "API port 8000 is already in use and did not answer health checks."
        }
    } else {
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-Command", $dashboardApiCommand) `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $apiOutLog `
            -RedirectStandardError $apiErrLog
    }

    if (Test-TcpPortInUse -Port 5173) {
        if (-not (Wait-HttpReady -Url $webUrl -TimeoutSeconds 5)) {
            throw "Dashboard port 5173 is already in use and did not answer HTTP requests."
        }
    } else {
        Start-Process -FilePath "npm.cmd" `
            -ArgumentList @("run", "dev:dashboard", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $webOutLog `
            -RedirectStandardError $webErrLog
    }

    if (-not (Wait-HttpReady -Url $apiUrl -TimeoutSeconds 30)) {
        throw "Dashboard API did not become ready at $apiUrl"
    }
    if (-not (Wait-HttpReady -Url $webUrl -TimeoutSeconds 30)) {
        throw "Dashboard web app did not become ready at $webUrl"
    }

    Start-Process $webUrl
} catch {
    Show-LauncherError $_.Exception.Message
    throw
}
