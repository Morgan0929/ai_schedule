param(
    [Parameter(Mandatory = $false)]
    [string]$BackendDir = "C:\deploy\ai-schedule\backend"
)

$ErrorActionPreference = "Stop"

$resolvedBackend = Resolve-Path -LiteralPath $BackendDir
$python = Join-Path $resolvedBackend "venv\Scripts\python.exe"
$logs = Join-Path $resolvedBackend "logs"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python"
}

New-Item -ItemType Directory -Force -Path $logs | Out-Null

$services = @(
    @{ Name = "app-service";      Script = "app_service\main.py";      Port = 8000 },
    @{ Name = "crawler-service";  Script = "crawler_service\main.py";  Port = 8001 },
    @{ Name = "agent-service";    Script = "agent_service\main.py";    Port = 8002 },
    @{ Name = "timeline-service"; Script = "timeline_service\main.py"; Port = 8003 },
    @{ Name = "rag-service";      Script = "rag_service\main.py";      Port = 8004 }
)

foreach ($service in $services) {
    $scriptPath = Join-Path $resolvedBackend $service.Script
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Service script not found: $scriptPath"
    }

    $existing = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "$($service.Name) appears to already be listening on port $($service.Port). Skipping."
        continue
    }

    $stdout = Join-Path $logs "$($service.Name).out.log"
    $stderr = Join-Path $logs "$($service.Name).err.log"
    Start-Process -FilePath $python `
        -ArgumentList $service.Script `
        -WorkingDirectory $resolvedBackend `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden

    Write-Host "Started $($service.Name) on port $($service.Port). Logs: $stdout / $stderr"
}

Write-Host "Health checks:"
foreach ($service in $services) {
    $url = "http://127.0.0.1:$($service.Port)/health"
    try {
        $result = Invoke-RestMethod -Uri $url -TimeoutSec 5
        Write-Host "$url OK"
    } catch {
        Write-Host "$url not ready: $($_.Exception.Message)"
    }
}
