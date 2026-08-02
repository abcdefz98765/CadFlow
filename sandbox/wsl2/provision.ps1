[CmdletBinding()]
param(
    [string]$RuntimeRoot = (Join-Path $env:LOCALAPPDATA "CadFlow\sandbox"),
    [string]$HostPython = ".venv-cadflow\Scripts\python.exe",
    [switch]$ResumeExisting,
    [switch]$RepairUnattested
)

$ErrorActionPreference = "Stop"
$DistroName = "CadFlow-Sandbox-CQ-v1"
$RootfsName = "ubuntu-jammy-wsl-amd64-wsl.rootfs.tar.gz"
$RootfsUri = "https://cloud-images.ubuntu.com/wsl/releases/22.04/20240304/$RootfsName"
$RootfsSha256 = "de9f6149da07b90350a3ccd94b4858b82fef71f0ec2982acb93de583c4c87585"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ManifestPath = Join-Path $PSScriptRoot "runtime_manifest.json"
$LockPath = Join-Path $PSScriptRoot "requirements-cp310.lock"
$DownloadRoot = Join-Path $RuntimeRoot "download-cache"
$Wheelhouse = Join-Path $DownloadRoot "wheelhouse-cp310"
$RootfsPath = Join-Path $DownloadRoot $RootfsName
$InstallRoot = Join-Path $RuntimeRoot "wsl\cadquery-v1"

function Assert-Hash([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) {
        throw "SHA-256 mismatch for $Path"
    }
}

if (-not (Test-Path -LiteralPath $HostPython -PathType Leaf)) {
    throw "Host Python was not found: $HostPython"
}
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is not installed"
}

$existing = @(wsl.exe --list --quiet | ForEach-Object { $_.Trim([char]0).Trim() })
if ($existing -contains $DistroName) {
    if (-not $ResumeExisting) {
        throw "$DistroName already exists. CadFlow never overwrites or unregisters a sandbox distro automatically."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot "ext4.vhdx") -PathType Leaf)) {
        throw "Resume refused because the registered distro is not at the expected CadFlow install path."
    }
    wsl.exe --distribution $DistroName --user root --exec test ! -e /opt/cadflow/runtime_manifest.json
    if ($LASTEXITCODE -ne 0) {
        if (-not $RepairUnattested) {
            throw "Resume refused because the existing distro contains runtime state. Use -RepairUnattested only after a failed attestation from this provisioner."
        }
        wsl.exe --distribution $DistroName --user root --exec test ! -e /opt/cadflow/ATTESTED
        if ($LASTEXITCODE -ne 0) {
            throw "Repair refused because the existing distro has an accepted attestation marker."
        }
    }
}

New-Item -ItemType Directory -Force -Path $DownloadRoot, $Wheelhouse | Out-Null
if (-not (Test-Path -LiteralPath $RootfsPath -PathType Leaf)) {
    Invoke-WebRequest -Uri $RootfsUri -OutFile $RootfsPath -UseBasicParsing
}
Assert-Hash $RootfsPath $RootfsSha256

$env:PIP_PROGRESS_BAR = "off"
& $HostPython -m pip download `
    --disable-pip-version-check `
    --require-hashes `
    --only-binary=:all: `
    --platform manylinux_2_31_x86_64 `
    --platform manylinux2014_x86_64 `
    --platform manylinux_2_17_x86_64 `
    --python-version 310 `
    --implementation cp `
    --abi cp310 `
    --dest $Wheelhouse `
    --requirement $LockPath
if ($LASTEXITCODE -ne 0) {
    throw "Pinned wheel download failed"
}

if ($existing -notcontains $DistroName) {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    wsl.exe --import $DistroName $InstallRoot $RootfsPath --version 2
    if ($LASTEXITCODE -ne 0) {
        throw "WSL import failed"
    }
}

$FinalWslConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot "wsl.conf") -Raw -Encoding utf8
$FinalWslConfigBase64 = [Convert]::ToBase64String(
    [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot "wsl.conf"))
)
$BuildWslConfig = $FinalWslConfig -replace 'generateResolvConf=false', 'generateResolvConf=true'
$BuildWslConfig | wsl.exe --distribution $DistroName --user root --exec tee /etc/wsl.conf | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not configure the isolated build phase"
}
wsl.exe --terminate $DistroName
wsl.exe --distribution $DistroName --user root --exec true
if ($LASTEXITCODE -ne 0) {
    throw "Could not restart the isolated build phase"
}

try {
    $StageLinux = "/tmp/cadflow-provision"
    $StageParent = Join-Path $RuntimeRoot "provision-staging"
    $StageHost = Join-Path $StageParent ([guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path (Join-Path $StageHost "wheelhouse") | Out-Null
    wsl.exe --distribution $DistroName --user root --exec bash -lc "rm -rf -- '$StageLinux'; install -d -m 0700 '$StageLinux'"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the controlled provisioning stage"
    }
    Copy-Item -LiteralPath $LockPath -Destination (Join-Path $StageHost "requirements-cp310.lock")
    Copy-Item -LiteralPath $ManifestPath -Destination (Join-Path $StageHost "runtime_manifest.json")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "worker.py") -Destination (Join-Path $StageHost "worker.py")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "probe.py") -Destination (Join-Path $StageHost "probe.py")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "cadflow-sandbox-launch") -Destination (Join-Path $StageHost "cadflow-sandbox-launch")
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "wsl.conf") -Destination (Join-Path $StageHost "wsl.conf")
    Copy-Item -Path (Join-Path $Wheelhouse "*.whl") -Destination (Join-Path $StageHost "wheelhouse")
    tar.exe -C $StageHost -cf - . | wsl.exe --distribution $DistroName --user root --exec tar -xf - -C $StageLinux
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stream the controlled provisioning payload into WSL"
    }
    wsl.exe --distribution $DistroName --user root --exec bash -lc @"
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3.10=3.10.12-1~22.04.16 \
  python3.10-venv=3.10.12-1~22.04.16 \
  python3-seccomp=2.5.3-2ubuntu3~22.04.1 \
  systemd=249.11-0ubuntu3.21 \
  libgl1=1.4.0-1 \
  libxrender1=1:0.9.10-1build4 \
  libsm6=2:1.2.3-1build2 \
  ca-certificates
id cadflow-worker >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin cadflow-worker
python3.10 -m venv --system-site-packages /opt/cadflow/venv
/opt/cadflow/venv/bin/pip install --disable-pip-version-check --no-index --require-hashes \
  --find-links '$StageLinux/wheelhouse' --requirement '$StageLinux/requirements-cp310.lock'
install -d -o root -g root -m 0755 /opt/cadflow /opt/cadflow/bin
install -d -o root -g root -m 0711 /var/lib/cadflow /var/lib/cadflow/candidates
install -o root -g root -m 0555 '$StageLinux/worker.py' /opt/cadflow/worker.py
install -o root -g root -m 0555 '$StageLinux/probe.py' /opt/cadflow/probe.py
install -o root -g root -m 0555 '$StageLinux/cadflow-sandbox-launch' /opt/cadflow/bin/cadflow-sandbox-launch
ln -sfn /opt/cadflow/probe.py /opt/cadflow/bin/cadflow-sandbox-probe
install -o root -g root -m 0444 '$StageLinux/requirements-cp310.lock' /opt/cadflow/requirements-cp310.lock
install -o root -g root -m 0444 '$StageLinux/runtime_manifest.json' /opt/cadflow/runtime_manifest.json
install -o root -g root -m 0444 '$StageLinux/wsl.conf' /etc/wsl.conf
find /opt/cadflow -xdev -type d -exec chmod go-w {} +
find /opt/cadflow -xdev -type f -exec chmod go-w {} +
rm -rf -- '$StageLinux'
"@
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox runtime installation failed"
    }
}
catch {
    Write-Error "Provisioning stopped ($($_.Exception.Message)). The partially imported distro was not unregistered: $DistroName"
    throw
}
finally {
    $FinalWslConfigBase64 | wsl.exe --distribution $DistroName --user root --exec bash -lc "base64 -d > /etc/wsl.conf" 2>$null
    wsl.exe --distribution $DistroName --user root --exec rm -f /etc/resolv.conf 2>$null
    wsl.exe --terminate $DistroName 2>$null
    if ($StageHost -and (Test-Path -LiteralPath $StageHost)) {
        $resolvedStage = [System.IO.Path]::GetFullPath($StageHost)
        $resolvedParent = [System.IO.Path]::GetFullPath($StageParent)
        if ($resolvedStage.StartsWith($resolvedParent + [System.IO.Path]::DirectorySeparatorChar)) {
            Remove-Item -LiteralPath $resolvedStage -Recurse -Force
        }
    }
}

wsl.exe --terminate $DistroName
if ($LASTEXITCODE -ne 0) {
    throw "Could not restart the sandbox distro after sealing it"
}

$env:CADFLOW_MODEL_PROGRAM_SANDBOX = "1"
$probeInput = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$probeRequest = @{
    schema_version = 1
    profile_digest = $probeInput.profile_digest
    toolchain_digest = $probeInput.toolchain_digest
} | ConvertTo-Json -Compress
$attestation = $probeRequest | wsl.exe --distribution $DistroName --user root --exec /opt/cadflow/bin/cadflow-sandbox-probe --json
if ($LASTEXITCODE -ne 0) {
    throw "The sealed runtime failed active attestation and remains unavailable"
}
$attestation | ConvertFrom-Json | ConvertTo-Json -Depth 8
wsl.exe --distribution $DistroName --user root --exec touch /opt/cadflow/ATTESTED
if ($LASTEXITCODE -ne 0) {
    throw "Could not record the successful local attestation marker"
}
Write-Host "Provisioned $DistroName. Set CADFLOW_MODEL_PROGRAM_SANDBOX=1 only for processes that should probe this runtime."
