### Argument ###

$ErrorActionPreference = "Stop"

$PYTHON_VERSION = "3.12.11"
$TAG = "20250828"  # update these by yourself
$TARGET = "x86_64-pc-windows-msvc"

################

Set-Location (Resolve-Path "$PSScriptRoot\..\..")

$url = "https://github.com/astral-sh/python-build-standalone/releases/download/${TAG}/cpython-${PYTHON_VERSION}+${TAG}-${TARGET}-install_only_stripped.tar.gz"

$DEST_DIR = "src-tauri\pyembed"
$TEMP_FILE = ".python-standalone.tar.gz"

if (Test-Path -LiteralPath "$DEST_DIR\python\python.exe") {
    Write-Host "Embedded Python is already available."
    exit 0
}

try {
    & curl.exe -L "$url" -o "$TEMP_FILE"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to download embedded Python."
    }
    New-Item -ItemType Directory -Force -Path "$DEST_DIR" | Out-Null
    & tar.exe -xzf "$TEMP_FILE" -C "$DEST_DIR"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract embedded Python."
    }
}
finally {
    Remove-Item "$TEMP_FILE" -ErrorAction SilentlyContinue
}
