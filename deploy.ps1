# One-time deploy of Piano Companion to GitHub Pages.
# Prereq: gh auth login   (sign in to GitHub once, then run this script)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

gh repo create piano-companion --public --source . --push
gh api -X POST "repos/{owner}/piano-companion/pages" -f "source[branch]=main" -f "source[path]=/"

$login = gh api user -q .login
Write-Host ""
Write-Host "Deployed. Your app will be live in ~1 minute at:"
Write-Host "  https://$login.github.io/piano-companion/" -ForegroundColor Green
Write-Host "Open it on your phone and use 'Add to Home Screen' to install."
