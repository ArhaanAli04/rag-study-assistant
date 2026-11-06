<#
.SYNOPSIS
    Docker-first dev helper for the RAG Study Assistant (there is no make on Windows).

.DESCRIPTION
    Runs docker compose with docker-compose.yml + docker-compose.override.yml (the dev stack:
    bind-mounted source, uvicorn --reload, CRA dev server).

      up     build and start the stack in the background, then show container status
      down   stop and remove the containers; volumes (database, uploads, logs, Redis) are kept
      logs   follow one service's logs (default: backend)
      test   run pytest inside a throwaway backend container (Python 3.11 / Linux, like CI)
      shell  open a shell in a running service (default: backend)

    To wipe the Docker data as well, run `docker compose down -v` yourself; it deletes the
    database, uploads and Redis volumes, so the helper deliberately doesn't offer it.

.EXAMPLE
    .\scripts\dev.ps1 up
    .\scripts\dev.ps1 logs frontend
    .\scripts\dev.ps1 test -k semantic_cache
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('up', 'down', 'logs', 'test', 'shell')]
    [string] $Command,

    # Service for logs/shell; for test, extra pytest arguments go here and after it.
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $Rest = @()
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Invoke-Compose {
    param([string[]] $Arguments)
    # docker writes progress to stderr; under 'Stop', Windows PowerShell 5.1 turns that into a
    # terminating error when output is redirected. Success is judged by the exit code instead.
    $ErrorActionPreference = 'Continue'
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Assert-EnvFile {
    # compose's env_file makes a missing .env a hard error with a less helpful message.
    if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
        throw ".env not found in $RepoRoot. Run: Copy-Item .env.example .env  (then fill in the REQUIRED values)"
    }
}

function Assert-PortsFree {
    # A venv backend (uvicorn) or host `npm start` on the same port makes compose fail midway.
    $ourContainers = @(docker ps --filter 'name=^rag-' --format '{{.Names}}')
    if ($ourContainers.Count -gt 0) { return }
    foreach ($port in 8000, 3000, 6380) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $listener) {
            $proc = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
            throw "Port $port is already in use by $($proc.ProcessName) (pid $($listener.OwningProcess)). Stop it first."
        }
    }
}

function Get-ServiceName {
    if ($Rest.Count -gt 0) { return $Rest[0] }
    return 'backend'
}

switch ($Command) {
    'up' {
        Assert-EnvFile
        Assert-PortsFree
        Invoke-Compose @('up', '--build', '--detach')
        Invoke-Compose @('ps')
        Write-Host "Frontend http://localhost:3000 | API http://localhost:8000/docs | logs: .\scripts\dev.ps1 logs"
    }
    'down' {
        Invoke-Compose @('down', '--remove-orphans')
    }
    'logs' {
        Invoke-Compose @('logs', '--follow', '--tail', '200', (Get-ServiceName))
    }
    'test' {
        Assert-EnvFile
        # --no-deps: the suite needs no Redis. The cache provider is off so pytest doesn't
        # write .pytest_cache into the bind-mounted tests/ folder.
        Invoke-Compose (@('run', '--rm', '--no-deps', 'backend',
                'python', '-m', 'pytest', '/app/backend/tests', '-q', '-p', 'no:cacheprovider') + $Rest)
    }
    'shell' {
        Invoke-Compose @('exec', (Get-ServiceName), 'sh')
    }
}
