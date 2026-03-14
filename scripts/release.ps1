# Usage: .\scripts\release.ps1 1.2.0
# Bumps manifest.json, commits, tags, and pushes — all in sync.
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ManifestPath = "custom_components\baillconnect\manifest.json"

# -- Argument check -----------------------------------------------------------
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Error "Version must follow semver format (e.g. 1.2.0)"
    exit 1
}

$Tag = "v$Version"

# -- Working tree must be clean -----------------------------------------------
$gitStatus = git status --porcelain
if ($gitStatus) {
    Write-Error "Working tree is not clean. Commit or stash your changes first."
    exit 1
}

# -- Tag must not already exist -----------------------------------------------
$existingTag = git tag | Where-Object { $_ -eq $Tag }
if ($existingTag) {
    Write-Error "Tag $Tag already exists."
    exit 1
}

# -- Update manifest.json -----------------------------------------------------
$ManifestAbsPath = (Resolve-Path $ManifestPath).Path
$ManifestJson    = Get-Content $ManifestAbsPath -Raw | ConvertFrom-Json
$CurrentVersion  = $ManifestJson.version
Write-Host "Bumping $CurrentVersion -> $Version in $ManifestPath"

$ManifestJson.version = $Version

# Write back as UTF-8 without BOM (required for HA / HACS)
$UpdatedJson = $ManifestJson | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ManifestAbsPath, $UpdatedJson + "`n", [System.Text.UTF8Encoding]::new($false))

# -- Commit -------------------------------------------------------------------
git add $ManifestPath
git commit -m "chore: bump version to $Version"

# -- Tag ----------------------------------------------------------------------
git tag -a $Tag -m "Release $Tag"
Write-Host "Created tag $Tag"

# -- Push ---------------------------------------------------------------------
Write-Host "Pushing commit and tag to origin..."
git push origin HEAD
git push origin $Tag

Write-Host ""
Write-Host "Release $Tag pushed. GitHub Actions will create the release automatically."
