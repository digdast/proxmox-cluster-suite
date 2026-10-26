@echo off
title Proxmox VE 5-Node Enterprise Cluster Orchestrator
color 0B
cd /d "%~dp0"
cls
echo =========================================================================
echo    PROXMOX VE 5-NODE ENTERPRISE CLUSTER ORCHESTRATOR
echo    Target Nodes: pve-00 .. pve-04 (192.168.0.30 - 192.168.0.34)
echo =========================================================================
echo.
python orchestrator.py
pause
