$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source }

function Invoke-Python([string[]]$PythonArguments) {
    & $pythonExe @PythonArguments
    if ($LASTEXITCODE -ne 0) { throw ('Python fallo: ' + ($PythonArguments -join ' ')) }
}

Invoke-Python -PythonArguments @('packaging\make_assets.py')
Invoke-Python -PythonArguments @('app.py','--self-test','.cache\validation\source.json')
if (-not ((Get-Content .cache\validation\source.json -Raw | ConvertFrom-Json).passed)) { throw 'Fallo prueba del codigo.' }
Invoke-Python -PythonArguments @('-m','PyInstaller','--noconfirm','--distpath','dist','--workpath','.cache\build','packaging\FaroPDF.spec')

$frozenReport=Join-Path $projectRoot '.cache\validation\frozen.json'
$frozenProcess=Start-Process -FilePath (Join-Path $projectRoot 'dist\FaroPDF\FaroPDF.exe') -ArgumentList @('--self-test',('"'+$frozenReport+'"')) -WindowStyle Hidden -Wait -PassThru
if ($frozenProcess.ExitCode -ne 0) { throw 'Fallo ejecutable empaquetado.' }
$frozenResult=Get-Content -LiteralPath $frozenReport -Raw | ConvertFrom-Json
if (-not $frozenResult.passed -or -not $frozenResult.frozen) { throw 'No paso la prueba del ejecutable.' }
Invoke-Python -PythonArguments @('packaging\validate_native.py')

$compilerDir=Join-Path $projectRoot '.cache\tools\InnoSetup'
$compiler=Join-Path $compilerDir 'ISCC.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $compilerDir -Parent) | Out-Null
    $compilerInstaller=Join-Path (Split-Path $compilerDir -Parent) 'innosetup-6.7.3.exe'
    Invoke-WebRequest -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe' -OutFile $compilerInstaller
    $expectedHash='9C73C3BAE7ED48D44112A0F48E66742C00090BDB5BEF71D9D3C056C66E97B732'
    if ((Get-FileHash -LiteralPath $compilerInstaller -Algorithm SHA256).Hash -ne $expectedHash) { throw 'SHA-256 del compilador no coincide.' }
    $vendorSignature=Get-AuthenticodeSignature -LiteralPath $compilerInstaller
    if ($vendorSignature.Status -ne 'Valid' -or $vendorSignature.SignerCertificate.Subject -notlike '*Pyrsys*') { throw 'Firma del compilador no verificada.' }
    $prepareCompiler=Start-Process -FilePath $compilerInstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="'+$compilerDir+'"')) -WindowStyle Hidden -Wait -PassThru
    if ($prepareCompiler.ExitCode -ne 0) { throw 'No se preparo Inno Setup.' }
}
& $compiler (Join-Path $PSScriptRoot 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Fallo compilacion del instalador.' }
& (Join-Path $PSScriptRoot 'validate_installer.ps1')
Compress-Archive -Path dist\FaroPDF\* -DestinationPath release\FaroPDF-1.1.0-Portable.zip -Force
Invoke-Python -PythonArguments @('packaging\release_manifest.py')
