param(
    [string[]]$CargoArguments = @('rustc','--release','--locked','-p','photocraft','--features','heif','--config','profile.release.package.photocraft-ui-egui.codegen-units=16','--','-C','codegen-units=16'),
    [string]$ToolsDirectory = '',
    [string]$TargetDirectory = ''
)
$ErrorActionPreference = 'Stop'
if (-not $ToolsDirectory) {
    $localTools = Join-Path $PSScriptRoot '.tools'
    $sharedTools = Join-Path (Split-Path $PSScriptRoot) 'FilmCraft\.tools'
    $ToolsDirectory = if (Test-Path -LiteralPath $localTools) { $localTools } else { $sharedTools }
}
if (Test-Path -LiteralPath (Join-Path $ToolsDirectory 'cargo\bin\cargo.exe')) {
    $env:CARGO_HOME = Join-Path $ToolsDirectory 'cargo'
    $env:RUSTUP_HOME = Join-Path $ToolsDirectory 'rustup'
    $env:PATH = (Join-Path $env:CARGO_HOME 'bin') + ';' + $env:PATH
}
if (Test-Path -LiteralPath (Join-Path $ToolsDirectory 'craft-fonts\fonts\manifest.txt')) {
    $env:CRAFT_FONTS_DIR = Join-Path $ToolsDirectory 'craft-fonts'
}
$env:CRAFT_FONTS_REQUIRED = '1'
$env:CARGO_BUILD_JOBS = '10'
$env:CARGO_TARGET_DIR = if ($TargetDirectory) { $TargetDirectory } else { Join-Path $PSScriptRoot 'target' }
$cargo = (Get-Command cargo.exe -ErrorAction Stop).Source
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Visual Studio C++ Build Tools are required.' }
$originalEnvironment = [Environment]::GetEnvironmentVariables('Process')
$originalPath = $env:PATH
Import-Module (Join-Path $vsRoot 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-no_logo -arch=x64 -host_arch=x64' | Out-Null
# Keep the toolchain paths while preserving Unicode user and project paths.
$compilerPath = ($env:PATH.Split(';') | Where-Object { $_ -notmatch '[^\x00-\x7F]' }) -join ';'
foreach ($key in $originalEnvironment.Keys) {
    if ($key -notin @('PATH','INCLUDE','LIB','LIBPATH')) {
        [Environment]::SetEnvironmentVariable($key, $originalEnvironment[$key], 'Process')
    }
}
$env:PATH = $compilerPath + ';' + $originalPath
Push-Location $PSScriptRoot
try {
    & $cargo @CargoArguments
    if ($LASTEXITCODE -ne 0) { throw "Cargo failed: $LASTEXITCODE" }
} finally { Pop-Location }
