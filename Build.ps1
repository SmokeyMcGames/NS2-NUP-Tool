$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Run .\Setup.ps1 first.'
}
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; the build was stopped.' }
& '.\.venv\Scripts\python.exe' tools/build_assets.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& '.\.venv\Scripts\python.exe' -m PyInstaller --clean --noconfirm 'NS2 NUP Tool.spec'
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$smokeReport = Join-Path $PSScriptRoot 'build\gui-smoke.json'
$smokeProcess = Start-Process -FilePath (Join-Path $PSScriptRoot 'dist\NS2 NUP Tool\NS2 NUP Tool.exe') -ArgumentList @('--smoke-test', ('"' + $smokeReport + '"')) -WindowStyle Hidden -PassThru
$null = $smokeProcess.Handle
if (-not $smokeProcess.WaitForExit(30000)) {
    $smokeProcess.Kill()
    throw 'The packaged GUI startup test timed out.'
}
$smokeProcess.Refresh()
$smokeResult = Get-Content -LiteralPath $smokeReport -Raw | ConvertFrom-Json
if ($smokeResult.status -ne 'ok' -or ($null -ne $smokeProcess.ExitCode -and $smokeProcess.ExitCode -ne 0)) {
    throw "Packaged GUI startup failed. See $smokeReport"
}
& '.\.venv\Scripts\python.exe' tools/portable_smoke.py
if ($LASTEXITCODE -ne 0) { throw 'Packaged conversion checks failed.' }
Write-Host "Portable app: $PSScriptRoot\dist\NS2 NUP Tool\NS2 NUP Tool.exe"
