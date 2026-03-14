# Usage: .\scripts\release.ps1 1.2.0
# Bumps manifest.json, commits, tags, and pushes — all in sync.
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$MANIFEST = "custom_components\baillconnect\manifest.json"

# ── Argument check ────────────────────────────────────────────────────────────
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Error "Version must follow semver format (e.g. 1.2.0)"
    exit 1
}

$Tag = "v$Version"

# ── Working tree must be clean ────────────────────────────────────────────────
$status = git status --porcelain
if ($status) {
    Write-Error "Working tree is not clean. Commit or stash your changes first."
    exit 1
}

# ── Tag must not already exist ────────────────────────────────────────────────
$existingTag = git tag | Where-Object { $_ -eq $Tag }
if ($existingTag) {
    Write-Error "Tag $Tag already exists."
    exit 1
}

# ── Update manifest.json ──────────────────────────────────────────────────────
$manifest = Get-Content $MANIFEST -Raw | ConvertFrom-Json
$currentVersion = $manifest.version
Write-Host "Bumping $currentVersion → $Version in $MANIFEST"

$manifest.version = $Version
$manifest | ConvertTo-Json -Depth 10 | Set-Content $MANIFEST -Encoding UTF8

# ConvertTo-Json adds BOM on some PS versions — normalize to UTF8 without BOM
$content = [System.IO.File]::ReadAllText((Resolve-Path $MANIFEST))
[System.IO.File]::WriteAllText((Resolve-Path $MANIFEST), $content, [System.Text.UTF8Encoding]::new($false))

# ── Commit ────────────────────────────────────────────────────────────────────
git add $MANIFEST
git commit -m "chore: bump version to $Version"

# ── Tag ───────────────────────────────────────────────────────────────────────
git tag -a $Tag -m "Release $Tag"
Write-Host "Created tag $Tag"

# ── Push ─────────────────────────────────────────────────────────────────────
Write-Host "Pushing commit and tag to origin..."
git push origin HEAD
git push origin $Tag

Write-Host ""
Write-Host "Release $Tag pushed. GitHub Actions will create the release automatically."
