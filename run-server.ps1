# Start the Piano Companion analysis service on http://127.0.0.1:8756
# First run: pip install -r server\requirements.txt   (and: winget install Gyan.FFmpeg)
Set-Location "$PSScriptRoot\server"
python main.py
