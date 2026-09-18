$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:SCIENTIFIC_READING_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
$env:TEMP = (Resolve-Path outputs/v02-004i/tmp).Path
$env:TMP = $env:TEMP
$env:PIP_NO_INDEX = '1'
$env:PIP_FIND_LINKS = (Resolve-Path outputs/v02-004i/wheels).Path
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$evidence = 'docs/codex-v02/V02-004I-evidence'
$runs = @()
function Run-Check($name, $exe, $arguments) {
    $started = [DateTime]::UtcNow.ToString('o')
    & $exe @arguments > "$evidence/$name.txt" 2>&1
    $code = $LASTEXITCODE
    $script:runs += [ordered]@{name=$name; command=$exe; args=$arguments; started=$started; exitCode=$code}
    $script:runs | ConvertTo-Json -Depth 8 | Set-Content "$evidence/runs.json"
    if ($code -ne 0) { throw "$name failed: $code" }
}
Run-Check 'build' 'npm.cmd' @('run', 'build')
Run-Check 'typecheck' 'npm.cmd' @('run', 'typecheck')
foreach ($name in @('v02-stop-control-api', 'full-read-pipeline', 'full-read-routes', 'current-runtime-boundary',
    'mineru-secret-boundary', 'task7-hidden-subprocess', 'library-assets-tools', 'review-engine-adapter', 'phase1-plugin-contract')) {
    Run-Check $name 'node.exe' @("tests/$name.mjs")
}
Write-Output "PASS: $($runs.Count) frozen-source build and related TS checks"
