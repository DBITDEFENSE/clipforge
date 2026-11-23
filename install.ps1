# ClipForge installer for Windows 10/11. In PowerShell, run:
#
#   irm https://raw.githubusercontent.com/DBITDEFENSE/clipforge/master/install.ps1 | iex
#
# It installs what ClipForge needs (uv, Node.js, ffmpeg) with winget, downloads ClipForge to
# %LOCALAPPDATA%\ClipForge, puts a ClipForge shortcut on the desktop and Start menu, and opens it.
# Running it again on a PC that already has ClipForge only repairs the tools and shortcuts.
# To install somewhere else, set $env:CLIPFORGE_DIR first.

$Repo = "DBITDEFENSE/clipforge"      # keep in sync with launcher.repo in config/settings.yaml
$Branch = "master"
$Dir = $env:CLIPFORGE_DIR
if (-not $Dir) { $Dir = Join-Path $env:LOCALAPPDATA "ClipForge" }

function Say($msg, $color = "Cyan") { Write-Host "[ClipForge] $msg" -ForegroundColor $color }
function Test-Tool($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Update-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Install-Tool($command, $wingetId, $label) {
    if (Test-Tool $command) { Say "$label is already installed."; return $true }
    if (-not (Test-Tool "winget")) {
        Say "$label is missing and winget isn't available to install it. Install 'App Installer' from the Microsoft Store, then run this again." "Red"
        return $false
    }
    Say "Installing $label..."
    winget install -e --id $wingetId --accept-source-agreements --accept-package-agreements | Out-Host
    Update-Path
    if (-not (Test-Tool $command)) { Say "$label was installed but isn't on PATH yet. Close this window, open a new PowerShell, and run the installer again." "Yellow"; return $false }
    return $true
}
function New-Shortcut($folder) {
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $folder "ClipForge.lnk"))
    $s.TargetPath = Join-Path $Dir "ClipForge.bat"
    $s.WorkingDirectory = $Dir
    $s.Description = "ClipForge: make, review and publish shorts"
    $s.Save()
}

Say "Installing to $Dir"
$ok = (Install-Tool "uv" "astral-sh.uv" "uv (Python manager)")
$ok = (Install-Tool "node" "OpenJS.NodeJS.LTS" "Node.js") -and $ok
$ok = (Install-Tool "ffmpeg" "Gyan.FFmpeg" "ffmpeg") -and $ok
if (-not $ok) { return }

if (Test-Path (Join-Path $Dir "pyproject.toml")) {
    Say "ClipForge is already installed here. Use the Update button in the launcher to get the latest version."
} else {
    $tmp = Join-Path $env:TEMP ("clipforge-install-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    try {
        Say "Downloading ClipForge..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -UseBasicParsing "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile (Join-Path $tmp "src.zip") -ErrorAction Stop
        Expand-Archive -Path (Join-Path $tmp "src.zip") -DestinationPath (Join-Path $tmp "x") -Force -ErrorAction Stop
        $src = Get-ChildItem (Join-Path $tmp "x") -Directory | Select-Object -First 1
        if (-not $src -or -not (Test-Path (Join-Path $src.FullName "pyproject.toml"))) { throw "the download doesn't look like ClipForge" }
        New-Item -ItemType Directory -Force $Dir | Out-Null
        Copy-Item -Path (Join-Path $src.FullName "*") -Destination $Dir -Recurse -Force -ErrorAction Stop
    } catch {
        Say "Download failed: $($_.Exception.Message)" "Red"
        return
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

New-Shortcut ([Environment]::GetFolderPath("Desktop"))
New-Shortcut ([Environment]::GetFolderPath("Programs"))
Say "Done. A ClipForge shortcut is on your desktop and in the Start menu." "Green"
Say "Opening ClipForge. The first start downloads its dependencies (several GB), so give it a while."
Start-Process (Join-Path $Dir "ClipForge.bat") -WorkingDirectory $Dir
