param([Parameter(Mandatory=$true)][string]$ConfigPath)
# Runs in inbox Windows PowerShell, outside Faro's Python/Qt DLLs. No policy or
# security settings are changed. The caller passes this reviewed script inline.
$ErrorActionPreference = 'Stop'
$gate = $null
$config = $null
$parentProcess = $null
$success = $false
$reopenFiles = @()
$requestedOpen = $false
$null = [Reflection.Assembly]::Load('System.Web.Extensions, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35')
$json = [Web.Script.Serialization.JavaScriptSerializer]::new()
function Write-Status([string]$State, [string]$Detail) {
    [IO.File]::WriteAllText($config.status, $json.Serialize(@{ state=$State; detail=$Detail; version=$config.version }))
}
try {
    # Only framework APIs: loading PowerShell utility/CIM modules on their first
    # use can otherwise take longer than the reader's closing handshake.
    $config = $json.DeserializeObject([IO.File]::ReadAllText($ConfigPath))
    if ([IO.File]::Exists($config.cancel)) { exit 1 }
    # Holding a reference keeps the gate alive after the closing reader exits.
    $gate = [Threading.Mutex]::new($false, 'Local\FaroPDF.Update')
    try { $parentProcess = [Diagnostics.Process]::GetProcessById($config.parent_pid) }
    catch [ArgumentException] {}
    if ($parentProcess) { $null = $parentProcess.Handle }
    [IO.File]::WriteAllText($config.ready, [string]$PID)
    Write-Status 'waiting' 'Esperando a que Faro termine completamente.'
    if ($parentProcess -and -not $parentProcess.WaitForExit(60000)) {
        throw 'Faro no termino a tiempo. La actualizacion se pospuso sin cambiar archivos.'
    }
    if ([IO.File]::Exists($config.cancel)) { throw 'Actualizacion cancelada antes de instalar.' }
    # The mutex covers native teardown; the process query also covers old
    # versions that predate this marker. Never close another user's document.
    $reader = $null
    try { $reader = [Threading.Mutex]::OpenExisting('Local\FaroPDF.Reader') }
    catch [Threading.WaitHandleCannotBeOpenedException] {}
    if ($reader) { $reader.Dispose(); throw 'Otra ventana de Faro sigue abierta. Actualizacion pospuesta.' }
    foreach ($other in [Diagnostics.Process]::GetProcessesByName('FaroPDF')) {
        try {
            if ([string]::Equals($other.MainModule.FileName, $config.executable, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Otra instancia de Faro sigue abierta. Actualizacion pospuesta.'
            }
        } finally { $other.Dispose() }
    }
    $package = [IO.FileInfo]::new($config.installer)
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($config.installer)
    try { $digest = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $hash.Dispose() }
    if ($package.Length -ne $config.size -or $digest -ne $config.sha256) {
        throw 'El instalador cambio despues de la verificacion. No se ejecuto.'
    }
    Write-Status 'installing' 'Instalando Faro. Puedes seguir el progreso en el instalador.'
    $arguments = @('/SP-', '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CURRENTUSER',
        '/NOCLOSEAPPLICATIONS', '/NOICONS', ('/DIR="'+$config.location+'"'), ('/LOG="'+$config.log+'"'))
    # /SILENT displays progress; /VERYSILENT used to make a long upgrade look
    # as if the reader had failed to close. Reopening is owned by this helper.
    $info = [Diagnostics.ProcessStartInfo]::new($config.installer, ($arguments -join ' '))
    $info.UseShellExecute = $false
    $info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Normal
    $setup = [Diagnostics.Process]::Start($info)
    $setup.WaitForExit()
    if ($setup.ExitCode -ne 0) { throw ('El instalador termino con codigo '+$setup.ExitCode+'. Revisa install.log.') }
    Write-Status 'installed' 'Actualizacion instalada correctamente.'
    $success = $true
} catch {
    if ($config) { Write-Status 'failed' $_.Exception.Message }
    else { [Console]::Error.WriteLine($_.Exception.Message) }
} finally {
    if ($parentProcess) { $parentProcess.Dispose() }
    if ($config) {
        $pending = [IO.Path]::Combine([IO.Path]::GetDirectoryName($config.status), 'pending-open')
        if ($success -and [IO.Directory]::Exists($pending)) {
            foreach ($request in [IO.Directory]::GetFiles($pending, '*.json')) {
                try {
                    $value = $json.DeserializeObject([IO.File]::ReadAllText($request))
                    $requestedOpen = $true
                    foreach ($file in @($value.files)) {
                        if ([IO.Path]::GetExtension($file) -eq '.pdf' -and [IO.File]::Exists($file)) {
                            $reopenFiles += $file
                        }
                    }
                    [IO.File]::Delete($request)
                } catch { # A malformed request must not prevent releasing the gate.
                }
            }
        }
    }
    if ($gate) { $gate.Dispose() }
    # No restart on failure: the bundle may need repair. Nothing is overwritten
    # while the reader is live, and no helper remains after setup has exited.
    if ($success -and ($config.reopen -or $requestedOpen)) {
        $unique = @{}
        if ($reopenFiles.Count) {
            foreach ($file in $reopenFiles) {
                if (-not $unique.ContainsKey($file)) {
                    $unique[$file] = $true
                    $info = [Diagnostics.ProcessStartInfo]::new($config.executable, ('"'+$file+'"'))
                    $info.UseShellExecute = $false
                    $null = [Diagnostics.Process]::Start($info)
                }
            }
        } else { $null = [Diagnostics.Process]::Start($config.executable) }
    }
}
if (-not $success) { exit 1 }
