$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$testRoot=Join-Path $projectRoot '.cache\validation\installer'
$target=Join-Path $testRoot 'Faro PDF'
if (Test-Path -LiteralPath $target) { throw 'La carpeta de validacion ya existe.' }
New-Item -ItemType Directory -Force -Path (Join-Path $target '_internal') | Out-Null
# Stale files must be removed on upgrade, not merely omitted from the new ZIP.
[IO.File]::WriteAllText((Join-Path $target '_internal\icuuc.dll'),'obsolete test fixture')
[IO.File]::WriteAllText((Join-Path $target '_internal\api-ms-win-core-test.dll'),'obsolete test fixture')
$setup=Join-Path $projectRoot 'release\FaroPDF-1.4.0-Instalar.exe'
$process=Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/VALIDATION=1',('/DIR="'+$target+'"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Fallo instalador aislado.' }
try {
    if (Test-Path -LiteralPath (Join-Path $target '_internal\icuuc.dll')) { throw 'Quedo ICU obsoleto.' }
    if (Get-ChildItem -LiteralPath (Join-Path $target '_internal') -Filter 'api-ms-win-*.dll') { throw 'Quedaron shims obsoletos.' }
    $report=Join-Path $testRoot 'installed.json'
    $run=Start-Process -FilePath (Join-Path $target 'FaroPDF.exe') -ArgumentList @('--self-test',('"'+$report+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($run.ExitCode -ne 0) { throw 'Fallo prueba del ejecutable instalado.' }
    $result=Get-Content -LiteralPath $report -Raw|ConvertFrom-Json
    if (-not $result.passed -or -not $result.frozen) { throw 'El ejecutable instalado no paso.' }
    [ordered]@{passed=$true;obsolete_dll_cleanup=$true;installed_engine=$result}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $projectRoot '.cache\validation\installer.json') -Encoding UTF8
} finally {
    $uninstall=Join-Path $target 'unins000.exe'
    if (Test-Path -LiteralPath $uninstall) {
        $cleanup=Start-Process -FilePath $uninstall -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($cleanup.ExitCode -ne 0) { throw 'Fallo desinstalacion aislada.' }
    }
}
