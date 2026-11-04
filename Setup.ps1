param(
    [string]$Python = 'py',
    [switch]$ReferenceTests
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$upstreamRevision = '744fb7e30ce3ace787f1839ee3e7f8a010e36c04'
if ($ReferenceTests -and -not (Test-Path -LiteralPath 'upstream')) {
    git clone https://github.com/a55uka/nup.git upstream
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone the upstream dependency.' }
    git -C upstream checkout --detach $upstreamRevision
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the pinned upstream revision.' }
}
if ($ReferenceTests) {
    $actualRevision = git -C upstream rev-parse HEAD
    if ($LASTEXITCODE -ne 0 -or $actualRevision -ne $upstreamRevision) {
        throw "Expected reference revision $upstreamRevision. The existing checkout was preserved."
    }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($Python -eq 'py') { & $Python -3.12 -m venv .venv }
    else { & $Python -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required to create the development environment.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Ready. Run .\.venv\Scripts\python.exe main.py, or .\Build.ps1.'
