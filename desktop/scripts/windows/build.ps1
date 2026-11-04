Set-Location (Resolve-Path "$PSScriptRoot\..\..")

$ErrorActionPreference = "Stop"
$PROJECT_NAME = "stratara"
$PYTHON = "src-tauri\pyembed\python\python.exe"

if (-not (Test-Path -LiteralPath $PYTHON)) {
    & "$PSScriptRoot\download-py.ps1"
}

$env:PYTAURI_STANDALONE = "1"
$env:PYO3_PYTHON = (Resolve-Path -LiteralPath $PYTHON).Path

& uv.exe pip install `
    --exact `
    --compile-bytecode `
    --python="$env:PYO3_PYTHON" `
    --reinstall-package="$PROJECT_NAME" `
    .\src-tauri
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install Stratara into embedded Python."
}

& .\node_modules\.bin\tauri.cmd build --config="src-tauri\tauri.bundle.json" -- --profile bundle-release
if ($LASTEXITCODE -ne 0) {
    throw "Tauri bundle build failed."
}
