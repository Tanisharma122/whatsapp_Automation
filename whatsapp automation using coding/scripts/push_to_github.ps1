# ============================================================
# push_to_github.ps1
# Syncs the Cloud-Kitchen folder to GitHub → whatsapp_Automation repo
# Usage:  .\scripts\push_to_github.ps1 -Message "your commit message"
# ============================================================

param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

# ── Config ────────────────────────────────────────────────────
$REMOTE_REPO    = "https://github.com/Tanisharma122/whatsapp_Automation"
$REMOTE_FOLDER  = "Cloud-Kitchen"
$PROJECT_ROOT   = $PSScriptRoot | Split-Path -Parent   # Cloud Kitchen/
$TEMP_DIR       = "$env:TEMP\ck_push_temp_$(Get-Random)"

# Files/folders to NEVER push
$EXCLUDE_DIRS   = @("venv", "__pycache__", ".pytest_cache", "logs", ".git")
$EXCLUDE_FILES  = @("*.env", "*.pyc", "*.pyo", "*.log")

# ── Commit message ────────────────────────────────────────────
if (-not $Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $Message = "chore: update Cloud-Kitchen project [$timestamp]"
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " Cloud Kitchen → GitHub Push" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host " Message : $Message" -ForegroundColor White
Write-Host " Remote  : $REMOTE_REPO" -ForegroundColor White
Write-Host " Folder  : $REMOTE_FOLDER" -ForegroundColor White
Write-Host ""

# ── Safety check: abort if .env would be copied ───────────────
$envCheck = Get-ChildItem "$PROJECT_ROOT\.env" -ErrorAction SilentlyContinue
if ($envCheck) {
    Write-Host "✅ .env found locally (will be EXCLUDED from push)" -ForegroundColor Green
}

# ── Step 1: Clone the remote repo ─────────────────────────────
Write-Host "[ 1/5 ] Cloning remote repo..." -ForegroundColor Yellow
git clone $REMOTE_REPO $TEMP_DIR --quiet
if ($LASTEXITCODE -ne 0) { throw "Clone failed!" }

# ── Step 2: Wipe old Cloud-Kitchen folder in clone ────────────
Write-Host "[ 2/5 ] Clearing old $REMOTE_FOLDER folder..." -ForegroundColor Yellow
$targetDir = "$TEMP_DIR\$REMOTE_FOLDER"
if (Test-Path $targetDir) {
    Remove-Item -Recurse -Force $targetDir
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

# ── Step 3: Copy project files (excluding secrets/junk) ───────
Write-Host "[ 3/5 ] Copying project files (secrets excluded)..." -ForegroundColor Yellow

robocopy $PROJECT_ROOT $targetDir /E `
    /XD venv __pycache__ .pytest_cache logs .git `
    /XF "*.env" "*.pyc" "*.pyo" "*.log" `
    /NFL /NDL /NJH /NJS | Out-Null

# Verify .env was NOT copied
$envLeak = Get-ChildItem "$targetDir\.env" -ErrorAction SilentlyContinue
if ($envLeak) {
    Write-Host "🚨 ABORT: .env was accidentally copied! Stopping." -ForegroundColor Red
    Remove-Item -Recurse -Force $TEMP_DIR
    exit 1
}

# ── Step 4: Commit ────────────────────────────────────────────
Write-Host "[ 4/5 ] Committing changes..." -ForegroundColor Yellow
Set-Location $TEMP_DIR

git config user.email "tanisharma122@gmail.com"
git config user.name  "Tanisharma122"
git add "$REMOTE_FOLDER/"

# Check if there's actually anything new to commit
$status = git status --porcelain
if (-not $status) {
    Write-Host ""
    Write-Host "⚠️  No changes detected vs remote — nothing to push." -ForegroundColor Magenta
    Set-Location $PROJECT_ROOT
    Remove-Item -Recurse -Force $TEMP_DIR
    exit 0
}

git commit -m $Message --quiet
if ($LASTEXITCODE -ne 0) { throw "Commit failed!" }

# ── Step 5: Push ──────────────────────────────────────────────
Write-Host "[ 5/5 ] Pushing to GitHub..." -ForegroundColor Yellow
git push origin main --quiet
if ($LASTEXITCODE -ne 0) { throw "Push failed!" }

# ── Cleanup ───────────────────────────────────────────────────
Set-Location $PROJECT_ROOT
Remove-Item -Recurse -Force $TEMP_DIR

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host " ✅ PUSHED SUCCESSFULLY!" -ForegroundColor Green
Write-Host " 🔗 $REMOTE_REPO/tree/main/$REMOTE_FOLDER" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host ""
