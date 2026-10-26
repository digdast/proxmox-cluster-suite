@echo off
title Proxmox VE Cluster Dashboard (Port 7880)
color 0A
cd /d "%~dp0"
cls
echo Starting Proxmox Cluster Web Dashboard on http://localhost:7880 ...
start http://localhost:7880
python web_dashboard.py
pause
