# Windows: repo kökünden çalıştır -> .\scripts\start-backend.ps1
Set-Location "$PSScriptRoot\..\backend"
if (-not (Test-Path venv)) { python -m venv venv }
& .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
