param(
    [switch]$Once
)

$ErrorActionPreference = "Stop"

# Check if .autoloop/local.json and .autoloop/config.json exist
$LocalJsonPath = Join-Path (Get-Location) ".autoloop\local.json"
$ConfigJsonPath = Join-Path (Get-Location) ".autoloop\config.json"

if (-not (Test-Path $LocalJsonPath)) {
    Write-Error "Error: .autoloop/local.json not found. Please create it first."
    exit 1
}

if (-not (Test-Path $ConfigJsonPath)) {
    Write-Error "Error: .autoloop/config.json not found. Please create it first."
    exit 1
}

# Load autoloop_home from local.json
try {
    $LocalConfig = Get-Content -Raw -Path $LocalJsonPath | ConvertFrom-Json
} catch {
    Write-Error "Error: Failed to parse .autoloop/local.json."
    exit 1
}

$AutoloopHome = $LocalConfig.autoloop_home
if (-not $AutoloopHome) {
    Write-Error "Error: 'autoloop_home' is not specified in .autoloop/local.json."
    exit 1
}

if (-not (Test-Path $AutoloopHome)) {
    Write-Error "Error: autoloop_home path '$AutoloopHome' does not exist."
    exit 1
}

$ControllerPath = Join-Path $AutoloopHome "controller.py"
if (-not (Test-Path $ControllerPath)) {
    Write-Error "Error: controller.py not found under autoloop_home: $ControllerPath"
    exit 1
}

# Build arguments
$ControllerArgs = @()
$ControllerArgs += "--config"
$ControllerArgs += ".autoloop\config.json"
if ($Once) {
    $ControllerArgs += "--once"
}

# Run Python controller
py "$ControllerPath" $ControllerArgs
