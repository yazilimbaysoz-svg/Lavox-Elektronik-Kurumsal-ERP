$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$compilerCandidates = @(
    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$compiler = $compilerCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $compiler) {
    throw "The built-in .NET Framework C# compiler was not found."
}

$desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
$setupPath = Join-Path $desktop "Lavox_ERP_Setup.exe"
$launcherDirectory = Join-Path $projectRoot "dist\Lavox_ERP"
$launcherPath = Join-Path $launcherDirectory "Lavox_ERP.exe"
$iconPath = Join-Path $projectRoot "assets\lavox.ico"
$launcherSource = Join-Path $projectRoot "desktop_launcher.cs"
$wizardSource = Join-Path $projectRoot "installer_wizard.cs"

if (-not (Test-Path $launcherSource) -or -not (Test-Path $wizardSource)) {
    throw "The native launcher or installer source file is missing."
}
if (-not (Test-Path $iconPath)) {
    throw "The Lavox application icon is missing."
}

New-Item -ItemType Directory -Force -Path $launcherDirectory | Out-Null
$stagingDirectory = Join-Path $env:TEMP ("lavox-setup-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stagingDirectory | Out-Null

try {
    $launcherArguments = @(
        "/nologo",
        "/target:winexe",
        "/platform:anycpu",
        "/codepage:65001",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Net.Http.dll",
        "/reference:System.Windows.Forms.dll",
        "/reference:System.Web.Extensions.dll",
        ("/win32icon:" + $iconPath),
        ("/out:" + $launcherPath),
        $launcherSource
    )
    & $compiler @launcherArguments
    if ($LASTEXITCODE -ne 0) {
        throw "The native Lavox launcher compilation failed."
    }

    foreach ($directoryName in @("backend", "frontend", "locales", "assets")) {
        $sourceDirectory = Join-Path $projectRoot $directoryName
        if (-not (Test-Path $sourceDirectory)) {
            throw ("Required project directory is missing: " + $directoryName)
        }

        $sourceFiles = Get-ChildItem -File -Recurse $sourceDirectory | Where-Object { ($_.FullName -notmatch "\\(__pycache__|\.git|dist|build)\\") -and ($_.Extension -notin @(".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log")) }
        foreach ($sourceFile in $sourceFiles) {
            $relativePath = $sourceFile.FullName.Substring($projectRoot.Length).TrimStart("\")
            $destinationPath = Join-Path $stagingDirectory $relativePath
            $destinationDirectory = Split-Path -Parent $destinationPath
            New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
            Copy-Item -LiteralPath $sourceFile.FullName -Destination $destinationPath -Force
        }
    }

    $runtimeRequirements = Join-Path $projectRoot "requirements-runtime.txt"
    if (-not (Test-Path $runtimeRequirements)) {
        throw "The Python runtime requirements manifest is missing."
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archivePath = Join-Path $stagingDirectory "Lavox_ProjectArchive.zip"
    $packageRoot = Join-Path $stagingDirectory "package-root"
    New-Item -ItemType Directory -Path $packageRoot | Out-Null
    foreach ($directoryName in @("backend", "frontend", "locales", "assets")) {
        Copy-Item -LiteralPath (Join-Path $stagingDirectory $directoryName) `
            -Destination $packageRoot -Recurse -Force
    }
    Copy-Item -LiteralPath $runtimeRequirements -Destination $packageRoot

    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $packageRoot,
        $archivePath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )

    $wizardArguments = @(
        "/nologo",
        "/target:winexe",
        "/platform:anycpu",
        "/codepage:65001",
        "/reference:System.dll",
        "/reference:System.Core.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.Windows.Forms.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        ("/win32icon:" + $iconPath),
        ("/resource:" + $archivePath + ",Lavox.ERP.ProjectArchive.zip"),
        ("/resource:" + $launcherPath + ",Lavox.ERP.Launcher.exe"),
        ("/out:" + $setupPath),
        $wizardSource
    )
    & $compiler @wizardArguments
    if ($LASTEXITCODE -ne 0) {
        throw "The native Lavox Setup Wizard compilation failed."
    }

    $setupItem = Get-Item -LiteralPath $setupPath
    $launcherItem = Get-Item -LiteralPath $launcherPath
    Write-Output ("Setup: {0} ({1:N0} bytes)" -f $setupItem.FullName, $setupItem.Length)
    Write-Output ("Launcher: {0} ({1:N0} bytes)" -f $launcherItem.FullName, $launcherItem.Length)
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
    }
}
