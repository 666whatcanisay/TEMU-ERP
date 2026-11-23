$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $taskRoot 'starter'
$originalPythonPath = $env:PYTHONPATH
$originalPyCache = $env:PYTHONPYCACHEPREFIX
try {
    $env:PYTHONPATH = $testRoot
    $env:PYTHONPYCACHEPREFIX = Join-Path $taskRoot '.cache/python'
    & python -X utf8 -m unittest discover -s (Join-Path $testRoot 'tests') -v
    if ($LASTEXITCODE -ne 0) { throw 'Domain checks failed.' }
    & python -X utf8 (Join-Path $PSScriptRoot 'validate_bundle.py')
    if ($LASTEXITCODE -ne 0) { throw 'Bundle checks failed.' }
} finally {
    $env:PYTHONPATH = $originalPythonPath
    $env:PYTHONPYCACHEPREFIX = $originalPyCache
}
