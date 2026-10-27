param(
    [string]$InputShp = $env:DHE_INPUT_SHP,
    [string[]]$Ids = @('2001', '2002'),
    [double]$Height = 10,
    [string]$IdField = 'osm_id'
)
$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = 'python' }
if (-not $InputShp) {
    & $pythonExe (Join-Path $PSScriptRoot 'run_workbench.py')
} else {
    & $pythonExe (Join-Path $PSScriptRoot 'extrude.py') --input $InputShp --ids @Ids --id-field $IdField --height $Height --output (Join-Path $PSScriptRoot 'output/extrusion_2001_2002.html')
}
exit $LASTEXITCODE
