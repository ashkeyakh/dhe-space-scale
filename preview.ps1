$ErrorActionPreference = 'Stop'
$previewPath = Join-Path $PSScriptRoot 'output\extrusion_2001_2002.html'
if (-not (Test-Path -LiteralPath $previewPath)) { throw 'Generate the visualization first with .\run.ps1' }
$edgeExe = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (Test-Path -LiteralPath $edgeExe) {
    Start-Process -FilePath $edgeExe -ArgumentList ('"' + $previewPath + '"')
} else {
    Start-Process -FilePath $previewPath
}
