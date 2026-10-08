# Emerager0DB installer for Windows.
#   irm https://falks.cyou/get.ps1 | iex
$ErrorActionPreference = "Stop"

$ApiUrl = if ($env:EMERAGER0DB_API_URL) { $env:EMERAGER0DB_API_URL } else { "https://falks.cyou/api/version" }
$InstallDir = if ($env:EMERAGER0DB_INSTALL_DIR) { $env:EMERAGER0DB_INSTALL_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\Emerager0DB" }
$DataDir = if ($env:EMERAGER0DB_HOME) { $env:EMERAGER0DB_HOME } else { Join-Path $HOME ".emerager0db" }

if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
    throw "Unsupported CPU architecture: $env:PROCESSOR_ARCHITECTURE. Windows x86_64 is the only published build."
}
$Key = "windows-x86_64"
$Asset = "Emerager0DB-$Key.exe"

Write-Host "Detected $Key"
$Manifest = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
$BinUrl = $Manifest.downloads.PSObject.Properties[$Key].Value
$SumsUrl = $Manifest.checksums
if (-not $BinUrl) { throw "No release is published for $Key yet." }
if (-not $SumsUrl) { throw "The release manifest has no checksum file." }

$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("emerager0db-" + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $Tmp | Out-Null
try {
    $BinPath = Join-Path $Tmp $Asset
    Write-Host "Downloading Emerager0DB..."
    Invoke-WebRequest -Uri $BinUrl -OutFile $BinPath -UseBasicParsing

    $SumsText = (Invoke-WebRequest -Uri $SumsUrl -UseBasicParsing).Content
    $Line = ($SumsText -split "`n") | Where-Object { $_ -match ("\s\*?" + [regex]::Escape($Asset) + "\s*$") } | Select-Object -First 1
    if (-not $Line) { throw "No checksum is listed for $Asset. Installation aborted." }
    $Expected = ($Line.Trim() -split '\s+')[0].ToLower()
    $Actual = (Get-FileHash -Algorithm SHA256 -Path $BinPath).Hash.ToLower()
    if ($Actual -ne $Expected) {
        throw "Checksum mismatch. The download was discarded and nothing was installed."
    }
    Write-Host "Checksum verified."

    New-Item -ItemType Directory -Force -Path $InstallDir, $DataDir | Out-Null
    $Target = Join-Path $InstallDir "Emerager0DB.exe"
    Copy-Item -Path $BinPath -Destination $Target -Force
    Write-Host "Installed to $Target"
}
finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$Entries = @()
if ($UserPath) { $Entries = $UserPath -split ";" | Where-Object { $_ } }
if ($Entries -notcontains $InstallDir) {
    $NewPath = (@($Entries + $InstallDir) -join ";")
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    Write-Host "Added $InstallDir to your user PATH."
}

& (Join-Path $InstallDir "Emerager0DB.exe") setup
if ($LASTEXITCODE -ne 0) { throw "Setup did not complete. Run: Emerager0DB setup" }

Write-Host ""
Write-Host "Completed!"
Write-Host ""
Write-Host "Restart your shell asap and do:"
Write-Host ""
Write-Host "    Emerager0DB"
