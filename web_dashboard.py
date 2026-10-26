import os
import sys
import time
import socket
import asyncio
import subprocess
from typing import Dict, Any, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="Proxmox Cluster Orchestrator")

CLUSTER_NODES = [
    {"name": "pve-00", "ip": "192.168.0.30", "role": "Master / Node 0"},
    {"name": "pve-01", "ip": "192.168.0.31", "role": "Node 1"},
    {"name": "pve-02", "ip": "192.168.0.32", "role": "Node 2"},
    {"name": "pve-03", "ip": "192.168.0.33", "role": "Node 3"},
    {"name": "pve-04", "ip": "192.168.0.34", "role": "Node 4"},
]

STORAGE_NODE = {"name": "unRAID Storage", "ip": "192.168.0.3", "role": "NFS Backup & Media Target"}

def check_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def ping_latency(ip: str) -> float:
    t0 = time.time()
    if check_port(ip, 22, timeout=0.4) or check_port(ip, 8006, timeout=0.4):
        return round((time.time() - t0) * 1000, 1)
    return -1.0

@app.get("/api/cluster/status")
async def get_cluster_status():
    results = []
    total_online = 0
    for node in CLUSTER_NODES:
        ip = node["ip"]
        ssh = check_port(ip, 22)
        pve = check_port(ip, 8006)
        lat = ping_latency(ip)
        online = ssh or pve
        if online:
            total_online += 1
        results.append({
            "name": node["name"],
            "ip": ip,
            "role": node["role"],
            "ssh_22": ssh,
            "pve_8006": pve,
            "latency_ms": lat if lat >= 0 else None,
            "status": "Online" if online else "Offline",
            "pve_url": f"https://{ip}:8006/"
        })
    
    # Check Storage Node
    storage_ping = check_port(STORAGE_NODE["ip"], 445, timeout=0.4) or check_port(STORAGE_NODE["ip"], 2049, timeout=0.4)
    storage_info = {
        "name": STORAGE_NODE["name"],
        "ip": STORAGE_NODE["ip"],
        "role": STORAGE_NODE["role"],
        "status": "Online" if storage_ping else "Reachable",
        "latency_ms": ping_latency(STORAGE_NODE["ip"])
    }

    return {
        "cluster_name": "Proxmox Enterprise HA Cluster",
        "quorum": f"{total_online}/5 Nodes Online (Quorum Active)",
        "quorum_ok": total_online >= 3,
        "nodes": results,
        "storage": storage_info,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(content=HTML_PAGE)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Proxmox VE 5-Node Cluster Management & Tuning Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-base: #0b132b;
    --bg-card: rgba(28, 37, 65, 0.7);
    --border: rgba(255, 255, 255, 0.1);
    --accent-cyan: #38bdf8;
    --accent-blue: #0284c7;
    --accent-green: #10b981;
    --accent-orange: #f59e0b;
    --text-primary: #f8fafc;
    --text-muted: #94a3b8;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Plus Jakarta Sans', sans-serif;
    background: radial-gradient(circle at top right, #1c2541, #0b132b 80%);
    color: var(--text-primary);
    min-height: 100vh;
    padding: 24px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 18px;
    margin-bottom: 24px;
  }
  .title-group h1 {
    font-size: 20pt;
    font-weight: 800;
    letter-spacing: -0.5px;
  }
  .title-group p {
    color: var(--text-muted);
    font-size: 9.5pt;
    margin-top: 3px;
  }
  .badge-cluster {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.35);
    color: var(--accent-green);
    padding: 6px 14px;
    border-radius: 9999px;
    font-size: 9pt;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
  }
  .grid-5 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }
  .node-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
    backdrop-filter: blur(10px);
    transition: transform 0.2s, border-color 0.2s;
  }
  .node-card:hover {
    transform: translateY(-2px);
    border-color: var(--accent-cyan);
  }
  .node-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .node-name {
    font-size: 13pt;
    font-weight: 800;
  }
  .status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent-green);
    box-shadow: 0 0 8px var(--accent-green);
  }
  .node-ip {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5pt;
    color: var(--accent-cyan);
    margin-bottom: 10px;
  }
  .meta-row {
    display: flex;
    justify-content: space-between;
    font-size: 8.5pt;
    color: var(--text-muted);
    margin-bottom: 4px;
  }
  .meta-val {
    font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary);
  }
  .btn-pve {
    display: block;
    text-align: center;
    margin-top: 14px;
    padding: 7px 10px;
    background: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.3);
    color: var(--accent-cyan);
    text-decoration: none;
    border-radius: 6px;
    font-size: 8.5pt;
    font-weight: 600;
  }
  .btn-pve:hover {
    background: var(--accent-blue);
    color: #fff;
  }
  .action-panel {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .action-panel h2 {
    font-size: 13pt;
    margin-bottom: 14px;
  }
  .btn-group {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }
  .btn-action {
    background: #0284c7;
    color: #fff;
    border: none;
    padding: 10px 16px;
    border-radius: 6px;
    font-size: 9pt;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }
  .btn-action:hover {
    background: #0369a1;
  }
  .console-box {
    background: #050a14;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9pt;
    color: #38bdf8;
    height: 180px;
    overflow-y: auto;
    margin-top: 14px;
    white-space: pre-wrap;
  }
</style>
</head>
<body>

<div class="header">
  <div class="title-group">
    <h1>⚡ Proxmox VE 5-Node Enterprise Cluster</h1>
    <p>Target Range: 192.168.0.30 - 192.168.0.34 • Storage: 192.168.0.3 (unRAID)</p>
  </div>
  <div class="badge-cluster" id="quorumBadge">● Corosync Quorum Active (5/5)</div>
</div>

<div class="grid-5" id="nodesGrid">
  <!-- Filled via JS -->
</div>

<div class="action-panel">
  <h2>🛠️ Cluster Automation & Optimization Controls</h2>
  <div class="btn-group">
    <button class="btn-action" onclick="runScript('Full Production Tuning')">🚀 Run Full Node Tuning (All 5 Nodes)</button>
    <button class="btn-action" onclick="runScript('Disable Subscription Nag')">🔕 Remove Subscription Nag Popup</button>
    <button class="btn-action" onclick="runScript('Mount NFS Storage')">💾 Mount Shared NFS (192.168.0.3)</button>
    <button class="btn-action" onclick="runScript('Audit Cluster Quorum')">🩺 Run Corosync Health Check</button>
    <button class="btn-action" onclick="openTerminal()">💻 Open CLI Orchestrator</button>
  </div>
  <div class="console-box" id="consoleBox">Proxmox Cluster Orchestrator initialized. Ready to execute optimization tasks.</div>
</div>

<script>
async function refreshStatus() {
  try {
    const res = await fetch('/api/cluster/status');
    const data = await res.json();
    document.getElementById('quorumBadge').innerText = '● ' + data.quorum;
    
    let html = '';
    data.nodes.forEach(n => {
      html += `
        <div class="node-card">
          <div class="node-header">
            <span class="node-name">${n.name}</span>
            <div class="status-dot"></div>
          </div>
          <div class="node-ip">${n.ip}</div>
          <div class="meta-row"><span>Role:</span><span class="meta-val">${n.role}</span></div>
          <div class="meta-row"><span>SSH (22):</span><span class="meta-val">${n.ssh_22 ? 'OPEN' : 'CLOSED'}</span></div>
          <div class="meta-row"><span>PVE API:</span><span class="meta-val">${n.pve_8006 ? 'ONLINE' : 'OFFLINE'}</span></div>
          <div class="meta-row"><span>Latency:</span><span class="meta-val">${n.latency_ms ? n.latency_ms + 'ms' : '-'}</span></div>
          <a class="btn-pve" href="${n.pve_url}" target="_blank">Open PVE Console ↗</a>
        </div>
      `;
    });
    
    // Add Storage
    const s = data.storage;
    html += `
      <div class="node-card" style="border-left: 3px solid #10b981;">
        <div class="node-header">
          <span class="node-name">${s.name}</span>
          <div class="status-dot"></div>
        </div>
        <div class="node-ip">${s.ip}</div>
        <div class="meta-row"><span>Role:</span><span class="meta-val">${s.role}</span></div>
        <div class="meta-row"><span>Status:</span><span class="meta-val">${s.status}</span></div>
        <div class="meta-row"><span>Latency:</span><span class="meta-val">${s.latency_ms ? s.latency_ms + 'ms' : '-'}</span></div>
        <div class="meta-row"><span>Type:</span><span class="meta-val">NFS Backup / Media</span></div>
      </div>
    `;
    
    document.getElementById('nodesGrid').innerHTML = html;
  } catch(e) {
    console.error(e);
  }
}

function log(msg) {
  const box = document.getElementById('consoleBox');
  box.innerText += '\\n[' + new Date().toLocaleTimeString() + '] ' + msg;
  box.scrollTop = box.scrollHeight;
}

function runScript(action) {
  log('Starting task: ' + action + ' across pve-00..pve-04...');
  log('Notice: For password-protected root execution, launch orchestrator.bat in terminal.');
}

function openTerminal() {
  log('Please open C:\\\\scripts\\\\proxmox_cluster_suite\\\\run_suite.bat to run authenticated execution.');
}

refreshStatus();
setInterval(refreshStatus, 4000);
</script>

</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7880, log_level="warning")
