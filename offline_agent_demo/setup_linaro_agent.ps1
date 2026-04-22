param(
    [string]$HostName = "192.168.150.1",
    [string]$Username = "linaro",
    [string]$RemoteHome = "/home/linaro",
    [string]$ModelFile = "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
    [string]$AgentToken = "",
    [switch]$SkipBuild,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-FileExists {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "Required file not found: $PathValue"
    }
}

function Invoke-Remote {
    param([string]$Command)
    & ssh "$Username@$HostName" $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Remote command failed: $Command"
    }
}

function Copy-ToRemote {
    param(
        [string]$LocalPath,
        [string]$RemotePath
    )
    & scp $LocalPath "${Username}@${HostName}:$RemotePath"
    if ($LASTEXITCODE -ne 0) {
        throw "Copy failed: $LocalPath -> $RemotePath"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$zipPath = Join-Path $scriptDir "llama.cpp-master.zip"
$modelPath = Join-Path $scriptDir $ModelFile
$serverPath = Join-Path $scriptDir "server.py"
$selfTestPath = Join-Path $scriptDir "self_test.py"
$patchHeaderPath = Join-Path $scriptDir "llama.cpp-src\llama.cpp-master\ggml\src\ggml-cpu\ggml-cpu-impl.h"

Assert-FileExists $zipPath
Assert-FileExists $modelPath
Assert-FileExists $serverPath
Assert-FileExists $selfTestPath
Assert-FileExists $patchHeaderPath

$remoteSrcDir = "$RemoteHome/src"
$remoteModelDir = "$RemoteHome/models"
$remoteAgentDir = "$RemoteHome/offline_agent_demo"
$remoteLlamaDir = "$remoteSrcDir/llama.cpp-master"
$remoteHeaderPath = "$remoteLlamaDir/ggml/src/ggml-cpu/ggml-cpu-impl.h"
$remoteModelPath = "$remoteModelDir/$ModelFile"

Write-Step "Preparing remote directories"
Invoke-Remote "mkdir -p $remoteSrcDir $remoteModelDir $remoteAgentDir"

Write-Step "Uploading model and agent files"
Copy-ToRemote $modelPath $remoteModelPath
Copy-ToRemote $serverPath "$remoteAgentDir/server.py"
Copy-ToRemote $selfTestPath "$remoteAgentDir/self_test.py"

if (-not $SkipBuild) {
    Write-Step "Uploading llama.cpp source archive"
    Copy-ToRemote $zipPath "$remoteSrcDir/llama.cpp-master.zip"

    Write-Step "Unpacking llama.cpp on linaro"
    Invoke-Remote "cd $remoteSrcDir && rm -rf llama.cpp-master && unzip -q llama.cpp-master.zip"

    Write-Step "Applying ARM/GCC compatibility header"
    Copy-ToRemote $patchHeaderPath $remoteHeaderPath

    Write-Step "Configuring llama.cpp"
    Invoke-Remote "cd $remoteLlamaDir && cmake -B build"

    Write-Step "Building llama-server"
    Invoke-Remote "cd $remoteLlamaDir && cmake --build build -j4 --target llama-server"
}

if (-not $SkipStart) {
    Write-Step "Writing startup script on linaro"
    $agentTokenEnv = ""
    if ($AgentToken) {
        $escapedAgentToken = $AgentToken.Replace("'", "'\''")
        $agentTokenEnv = "AGENT_TOKEN='$escapedAgentToken' "
    }
    $startScript = @"
#!/bin/sh
pkill -f /home/linaro/src/llama.cpp-master/build/bin/llama-server >/dev/null 2>&1 || true
pkill -f /home/linaro/offline_agent_demo/server.py >/dev/null 2>&1 || true
nohup /home/linaro/src/llama.cpp-master/build/bin/llama-server -m $remoteModelPath --host 127.0.0.1 --port 8080 >$remoteAgentDir/llama-server.log 2>&1 &
sleep 3
cd $remoteAgentDir || exit 1
nohup env ${agentTokenEnv}AGENT_BACKEND=openai_compat MODEL_BASE_URL=http://127.0.0.1:8080 MODEL_NAME=qwen2.5-coder-0.5b-instruct python3 $remoteAgentDir/server.py --host 0.0.0.0 --port 8765 >$remoteAgentDir/agent-server.log 2>&1 &
"@

    $tmpScript = Join-Path $env:TEMP "start_linaro_agent.sh"
    Set-Content -LiteralPath $tmpScript -Value $startScript -NoNewline
    try {
        Copy-ToRemote $tmpScript "$remoteAgentDir/start_services.sh"
    }
    finally {
        Remove-Item -LiteralPath $tmpScript -Force -ErrorAction SilentlyContinue
    }

    Invoke-Remote "chmod +x $remoteAgentDir/start_services.sh && $remoteAgentDir/start_services.sh"

    Write-Step "Checking health endpoints"
    Invoke-Remote "curl -s http://127.0.0.1:8080/health && echo && curl -s http://127.0.0.1:8765/health"

    Write-Step "Running remote self-test"
    if ($AgentToken) {
        Invoke-Remote "env AGENT_TOKEN='$escapedAgentToken' python3 $remoteAgentDir/self_test.py"
    }
    else {
        Invoke-Remote "python3 $remoteAgentDir/self_test.py"
    }
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Agent server URL: http://$HostName:8765"
Write-Host "Client command: python `"$scriptDir\client.py`""
Write-Host ""
Write-Host "Options:"
Write-Host "  - Skip rebuild: .\setup_linaro_agent.ps1 -SkipBuild"
Write-Host "  - Skip restart: .\setup_linaro_agent.ps1 -SkipStart"
Write-Host "  - Enable token: .\setup_linaro_agent.ps1 -AgentToken `"your-token`""
