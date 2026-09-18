param([switch]$Remaining)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:SCIENTIFIC_READING_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
# Nested asset fixtures exceed MAX_PATH under the long worktree path.
New-Item -ItemType Directory -Force C:/tmp/v02-004i-ts | Out-Null
$env:TEMP = (Resolve-Path C:/tmp/v02-004i-ts).Path
$env:TMP = $env:TEMP
$env:PIP_NO_INDEX = '1'
$env:PIP_FIND_LINKS = (Resolve-Path outputs/v02-004i/wheels).Path
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$evidence = 'docs/codex-v02/V02-004I-evidence'
$runs = if ($Remaining) { @(Get-Content "$evidence/runs.json" -Raw | ConvertFrom-Json) } else { @() }
function Run-Check($name, $exe, $arguments) {
    $started = [DateTime]::UtcNow.ToString('o')
    if (Test-Path "$evidence/$name.txt") { Copy-Item "$evidence/$name.txt" "$evidence/$name-previous.txt" }
    & $exe @arguments > "$evidence/$name.txt" 2>&1
    $code = $LASTEXITCODE
    $script:runs += [ordered]@{name=$name; command=$exe; args=$arguments; started=$started; exitCode=$code}
    $script:runs | ConvertTo-Json -Depth 8 | Set-Content "$evidence/runs.json"
    if ($code -ne 0) { throw "$name failed: $code" }
}
if (!$Remaining) {
    Run-Check 'build' 'npm.cmd' @('run', 'build')
    Run-Check 'typecheck' 'npm.cmd' @('run', 'typecheck')
}
$names = if ($Remaining) { @('library-assets-tools', 'review-engine-adapter', 'phase1-plugin-contract') } else {
    @('v02-stop-control-api', 'full-read-pipeline', 'full-read-routes', 'current-runtime-boundary',
    'mineru-secret-boundary', 'task7-hidden-subprocess', 'library-assets-tools', 'review-engine-adapter', 'phase1-plugin-contract')
}
foreach ($name in $names) {
    Run-Check $name 'node.exe' @("tests/$name.mjs")
}
Write-Output "PASS: $($runs.Count) frozen-source build and related TS checks"
