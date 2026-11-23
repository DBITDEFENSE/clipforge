# ClipForge launcher (ClipForge.bat runs this). Keeps dependencies installed, runs the launcher page, and applies
# updates when the page asks for one (the page exits with code 42 after writing data\update-request.json).
#
# Updating never touches your work: .env, data\, out\, work\, inbox\, takes\ and your music/gameplay files are not in
# the download. Config files you edited are copied to config\backup\ before the new defaults replace them.
#
#   -UpdateOnly   apply an update and exit (no launcher page)
#   -ZipPath      update from a local zip instead of downloading (offline installs, testing)
#   -SkipSync     don't install Python/Node dependencies (testing)
param([switch]$UpdateOnly, [string]$ZipPath = "", [string]$Repo = "", [string]$Branch = "", [switch]$SkipSync)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
try { $Host.UI.RawUI.WindowTitle = "ClipForge" } catch {}

function Say($msg, $color = "Cyan") { Write-Host "[ClipForge] $msg" -ForegroundColor $color }
function Wait-Key { if ([Environment]::UserInteractive -and -not $UpdateOnly) { Read-Host "Press Enter to close" | Out-Null } }
function Test-Tool($name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Test-DevCheckout { return (Test-Path (Join-Path $Root ".git")) }

# Installs/updates Python and Node dependencies. Output goes to the window; returns $true on success.
function Sync-Deps {
    if ($SkipSync) { return $true }
    Say "Checking Python dependencies (the first time downloads several GB, including PyTorch)..."
    if (Test-DevCheckout) { uv sync | Out-Host } else { uv sync --frozen --no-dev | Out-Host }
    if ($LASTEXITCODE -ne 0) { return $false }
    Say "Checking the video renderer..."
    Push-Location (Join-Path $Root "render")
    npm install --no-audit --no-fund | Out-Host
    $ok = ($LASTEXITCODE -eq 0)
    Pop-Location
    return $ok
}

# Replaces the program files with the latest version. Returns "" on success, or the reason it failed.
function Update-App($repo, $branch) {
    if (Test-DevCheckout) {
        Say "This is a git checkout: pulling the latest commits..."
        git pull --ff-only | Out-Host
        if ($LASTEXITCODE -ne 0) { return "git pull failed. Commit or stash your changes, then update again." }
        return ""
    }
    if (-not $ZipPath) {
        if ($repo -notmatch '^[\w.-]+/[\w.-]+$' -or $branch -notmatch '^[\w./-]+$') { return "The update source isn't set (launcher.repo in config\settings.yaml)." }
    }
    $tmp = Join-Path $env:TEMP ("clipforge-update-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force $tmp | Out-Null
    try {
        $zip = $ZipPath
        if (-not $zip) {
            $zip = Join-Path $tmp "src.zip"
            Say "Downloading the latest version from github.com/$repo..."
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            $ProgressPreference = "SilentlyContinue"
            Invoke-WebRequest -UseBasicParsing "https://github.com/$repo/archive/refs/heads/$branch.zip" -OutFile $zip -ErrorAction Stop
        }
        Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp "x") -Force -ErrorAction Stop
        $src = Get-ChildItem (Join-Path $tmp "x") -Directory | Select-Object -First 1
        if (-not $src -or -not (Test-Path (Join-Path $src.FullName "pyproject.toml")) -or -not (Test-Path (Join-Path $src.FullName "clipforge"))) {
            return "The download doesn't look like ClipForge. Nothing was changed."
        }
        # Keep a copy of any config file that differs from the incoming one.
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        foreach ($f in Get-ChildItem (Join-Path $Root "config") -File -ErrorAction SilentlyContinue) {
            $new = Join-Path $src.FullName ("config\" + $f.Name)
            if ((Test-Path $new) -and ((Get-FileHash $f.FullName).Hash -ne (Get-FileHash $new).Hash)) {
                $bak = Join-Path $Root "config\backup\$stamp"
                New-Item -ItemType Directory -Force $bak | Out-Null
                Copy-Item $f.FullName $bak -ErrorAction Stop
                Say "Your edited config\$($f.Name) was saved to config\backup\$stamp" "Yellow"
            }
        }
        # Clear the code folders first so files removed upstream don't linger.
        foreach ($d in @("clipforge", "render\src", "tests")) {
            $old = Join-Path $Root $d
            if ((Test-Path (Join-Path $src.FullName $d)) -and (Test-Path $old)) { Remove-Item -Recurse -Force $old -ErrorAction Stop }
        }
        Copy-Item -Path (Join-Path $src.FullName "*") -Destination $Root -Recurse -Force -ErrorAction Stop
        return ""
    } catch {
        return "Update failed: $($_.Exception.Message)"
    } finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

function Invoke-Update($repo, $branch) {
    $err = Update-App $repo $branch
    if (-not $err -and -not (Sync-Deps)) { $err = "The new files are in place, but installing dependencies failed. Reopen ClipForge to retry." }
    $data = Join-Path $Root "data"
    New-Item -ItemType Directory -Force $data | Out-Null
    $msg = "Updated."
    if ($err) { $msg = $err }
    @{ ok = (-not $err); message = $msg; at = (Get-Date -Format "s") } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $data "update-result.json")
    Remove-Item (Join-Path $data "update-request.json") -ErrorAction SilentlyContinue
    if ($err) { Say $err "Red" } else { Say "Update complete." "Green" }
    return (-not $err)
}

if (-not (Test-Tool "uv")) {
    Say "uv (the Python manager) isn't installed. Run install.ps1 first: it sets up everything ClipForge needs." "Red"
    Wait-Key; exit 1
}

if ($UpdateOnly) {
    if (Invoke-Update $Repo $Branch) { exit 0 } else { exit 1 }
}

if (-not (Test-Path (Join-Path $Root ".venv")) -or -not (Test-Path (Join-Path $Root "render\node_modules\remotion"))) {
    if (-not (Sync-Deps)) { Say "Setup didn't finish. Check your internet connection and open ClipForge again." "Red"; Wait-Key; exit 1 }
}

$env:CLIPFORGE_SUPERVISED = "1"
uv run --no-sync clipforge launcher
$code = $LASTEXITCODE

if ($code -eq 42) {
    $req = $null
    try { $req = Get-Content (Join-Path $Root "data\update-request.json") -Raw -ErrorAction Stop | ConvertFrom-Json } catch {}
    if ($req) { Invoke-Update $req.repo $req.branch | Out-Null } else { Say "Update was requested but the request file is missing." "Red" }
    # Start again with the (possibly new) launcher script.
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "launcher.ps1")
    exit $LASTEXITCODE
}
if ($code -ne 0) { Say "ClipForge stopped with an error (code $code). The message is above." "Red"; Wait-Key }
exit $code
