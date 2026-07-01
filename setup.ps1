# setup.ps1 - one-time install on Windows.
# Right-click > "Run with PowerShell", or in a terminal:  .\setup.ps1

Write-Host "== Instagram non-follower cleaner - setup ==" -ForegroundColor Cyan

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python is not installed. Get it from https://www.python.org/downloads/ (tick 'Add to PATH')." -ForegroundColor Red
    exit 1
}
python --version

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Installing dependencies..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "Next: run a dry-run (nothing gets removed):" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe clean_followers.py"
