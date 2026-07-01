$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$logDir = Join-Path $repoRoot "tmp\launcher"
$apiLog = Join-Path $logDir "dashboard-api.log"
$webLog = Join-Path $logDir "dashboard-web.log"
$apiUrl = "http://127.0.0.1:8000/api/health"
$webUrl = "http://127.0.0.1:5173/"

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

try {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    if (-not (Test-Path $pythonExe)) {
        throw "Missing Python virtual environment at $pythonExe"
    }
    if (-not (Test-Path (Join-Path $repoRoot "node_modules"))) {
        throw "Missing node_modules. Run npm.cmd install first."
    }

    Start-Process -FilePath $pythonExe `
        -ArgumentList @("-m", "app", "dashboard-api", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $apiLog `
        -RedirectStandardError $apiLog

    Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev:dashboard", "--", "--port", "5173") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $webLog `
        -RedirectStandardError $webLog

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
