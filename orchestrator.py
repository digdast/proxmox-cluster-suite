#!/usr/bin/env python3
"""
Proxmox VE 5-Node Enterprise Cluster Orchestrator
Automates performance tuning, nag removal, NFS storage, and K3s provisioning across 192.168.0.30-34.
"""
import os
import sys
import time
import socket
import getpass
import datetime
from concurrent.futures import ThreadPoolExecutor
import paramiko

# Nodes mapping
CLUSTER_NODES = [
    {"name": "pve-00", "ip": "192.168.0.30"},
    {"name": "pve-01", "ip": "192.168.0.31"},
    {"name": "pve-02", "ip": "192.168.0.32"},
    {"name": "pve-03", "ip": "192.168.0.33"},
    {"name": "pve-04", "ip": "192.168.0.34"},
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    banner = f"""
{Colors.CYAN}{Colors.BOLD}========================================================================
   PROXMOX VE 5-NODE ENTERPRISE CLUSTER ORCHESTRATOR & TUNING SUITE
   Cluster Nodes: pve-00 .. pve-04 | Range: 192.168.0.30 - 192.168.0.34
========================================================================{Colors.ENDC}
"""
    print(banner)

def check_port(ip, port, timeout=0.8):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except:
        return False

def audit_cluster_health():
    print(f"\n{Colors.BOLD}[*] Scanning 5-Node Cluster Topology & Service Status...{Colors.ENDC}\n")
    print(f"{'Node':<10} {'IP Address':<16} {'SSH (22)':<12} {'PVE Web (8006)':<16} {'Status'}")
    print("-" * 65)
    
    online_count = 0
    for node in CLUSTER_NODES:
        ip = node["ip"]
        name = node["name"]
        ssh_ok = check_port(ip, 22)
        pve_ok = check_port(ip, 8006)
        
        status_str = f"{Colors.GREEN}ONLINE{Colors.ENDC}" if (ssh_ok and pve_ok) else f"{Colors.FAIL}DEGRADED{Colors.ENDC}"
        if ssh_ok and pve_ok:
            online_count += 1
            
        ssh_str = f"{Colors.GREEN}OPEN{Colors.ENDC}" if ssh_ok else f"{Colors.FAIL}CLOSED{Colors.ENDC}"
        pve_str = f"{Colors.GREEN}ACTIVE{Colors.ENDC}" if pve_ok else f"{Colors.FAIL}UNREACHABLE{Colors.ENDC}"
        print(f"{name:<10} {ip:<16} {ssh_str:<21} {pve_str:<25} {status_str}")
        
    print("-" * 65)
    print(f"Health Summary: {online_count}/5 Nodes Fully Operational\n")
    return online_count == 5

def execute_on_node(node, username, password, key_path, commands):
    name = node["name"]
    ip = node["ip"]
    log_file = os.path.join(LOGS_DIR, f"{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        if key_path and os.path.exists(key_path):
            client.connect(ip, port=22, username=username, key_filename=key_path, timeout=10)
        else:
            client.connect(ip, port=22, username=username, password=password, timeout=10)
            
        print(f"{Colors.GREEN}[✓] Connected to {name} ({ip}){Colors.ENDC}")
        
        with open(log_file, "w", encoding="utf-8") as f_log:
            f_log.write(f"=== Execution Log for {name} ({ip}) ===\n\n")
            for cmd in commands:
                f_log.write(f"\n--- COMMAND: {cmd} ---\n")
                stdin, stdout, stderr = client.exec_command(cmd)
                out = stdout.read().decode('utf-8', errors='replace')
                err = stderr.read().decode('utf-8', errors='replace')
                f_log.write(out)
                if err:
                    f_log.write(f"[STDERR]\n{err}\n")
                
        client.close()
        print(f"{Colors.GREEN}[✓] Finished tasks on {name} - Log: {log_file}{Colors.ENDC}")
        return True, name, "SUCCESS"
    except Exception as e:
        print(f"{Colors.FAIL}[✗] Error on {name} ({ip}): {str(e)}{Colors.ENDC}")
        return False, name, str(e)

def upload_and_run_script(node, username, password, key_path, local_script_path, remote_path):
    name = node["name"]
    ip = node["ip"]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_path and os.path.exists(key_path):
            client.connect(ip, port=22, username=username, key_filename=key_path, timeout=10)
        else:
            client.connect(ip, port=22, username=username, password=password, timeout=10)
            
        sftp = client.open_sftp()
        sftp.put(local_script_path, remote_path)
        sftp.close()
        
        # Make executable and run
        cmd = f"chmod +x {remote_path} && bash {remote_path}"
        stdin, stdout, stderr = client.exec_command(cmd)
        
        # Stream output in real time
        print(f"\n{Colors.CYAN}--- [{name} ({ip}) Stream] ---{Colors.ENDC}")
        for line in iter(stdout.readline, ""):
            print(f"[{name}] {line.strip()}")
            
        err = stderr.read().decode('utf-8', errors='replace')
        if err:
            print(f"{Colors.WARNING}[{name} STDERR] {err[:200]}{Colors.ENDC}")
            
        client.close()
        return True, name
    except Exception as e:
        print(f"{Colors.FAIL}[✗] Failed execution on {name} ({ip}): {e}{Colors.ENDC}")
        return False, name

def main():
    print_banner()
    audit_cluster_health()
    
    print(f"{Colors.BOLD}Select an action to perform:{Colors.ENDC}")
    print("  [1] Run Full Production Tuning on All Nodes (No-Sub repo, Disable Nag, CPU Governor, Sysctl, ZFS ARC)")
    print("  [2] Configure Shared NFS Backup Storage (Target: 192.168.0.3 / unRAID)")
    print("  [3] Provision HA K3s Kubernetes LXC Container")
    print("  [4] Run Corosync Quorum & Cluster Health Check")
    print("  [5] Launch Local Web Dashboard GUI")
    print("  [0] Exit")
    
    choice = input("\nEnter choice [1-5]: ").strip()
    
    if choice == "5":
        print(f"\n{Colors.GREEN}Launching Proxmox Cluster Web Dashboard on http://localhost:7880 ...{Colors.ENDC}")
        import subprocess
        subprocess.Popen([sys.executable, os.path.join(SCRIPT_DIR, "web_dashboard.py")])
        time.sleep(1)
        os.system("start http://localhost:7880")
        return
        
    if choice == "0":
        print("Exiting.")
        return
        
    username = input("\nEnter SSH username [default: root]: ").strip() or "root"
    auth_choice = input("Authenticate with [P]assword or SSH [K]ey? (P/K) [default: P]: ").strip().upper() or "P"
    
    password = None
    key_path = None
    if auth_choice == "K":
        key_path = input("Enter path to private key [e.g. C:\\Users\\efrai\\.ssh\\id_rsa]: ").strip()
    else:
        password = getpass.getpass("Enter root password: ")

    if choice == "1":
        script_file = os.path.join(SCRIPT_DIR, "optimize_node.sh")
        print(f"\n{Colors.BOLD}[*] Deploying Production Tuning Suite to all 5 nodes concurrently...{Colors.ENDC}")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(upload_and_run_script, node, username, password, key_path, script_file, "/tmp/optimize_node.sh")
                for node in CLUSTER_NODES
            ]
            for f in futures:
                f.result()
        print(f"\n{Colors.GREEN}{Colors.BOLD}[✓] Production Tuning Completed Across Cluster!{Colors.ENDC}\n")

    elif choice == "2":
        nfs_server = input("Enter NFS Server IP [default: 192.168.0.3]: ").strip() or "192.168.0.3"
        nfs_export = input("Enter NFS Export Path [default: /mnt/user/data/backups]: ").strip() or "/mnt/user/data/backups"
        script_file = os.path.join(SCRIPT_DIR, "setup_nfs_backups.sh")
        # Run on master node pve-00 (storage configuration is cluster-wide)
        master_node = CLUSTER_NODES[0]
        print(f"\n{Colors.BOLD}[*] Registering NFS Storage and Backup Schedules via {master_node['name']}...{Colors.ENDC}")
        upload_and_run_script(master_node, username, password, key_path, script_file, f"/tmp/setup_nfs_backups.sh {nfs_server} {nfs_export}")

    elif choice == "3":
        ct_id = input("Enter Container ID [default: 200]: ").strip() or "200"
        ct_name = input("Enter Container Name [default: k3s-master-01]: ").strip() or "k3s-master-01"
        ct_ip = input("Enter Container Static IP/CIDR [default: 192.168.0.40/24]: ").strip() or "192.168.0.40/24"
        script_file = os.path.join(SCRIPT_DIR, "k3s_lxc_setup.sh")
        master_node = CLUSTER_NODES[0]
        print(f"\n{Colors.BOLD}[*] Provisioning nested K3s container on {master_node['name']}...{Colors.ENDC}")
        upload_and_run_script(master_node, username, password, key_path, script_file, f"/tmp/k3s_lxc_setup.sh {ct_id} {ct_name} {ct_ip}")

    elif choice == "4":
        cmds = [
            "hostname",
            "pveversion",
            "pvecm status || echo 'Not clustered'",
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'Gov: unknown'",
            "sysctl vm.swappiness",
            "pvesm status"
        ]
        print(f"\n{Colors.BOLD}[*] Auditing Cluster Health & Quorum across all 5 nodes...{Colors.ENDC}")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(execute_on_node, node, username, password, key_path, cmds)
                for node in CLUSTER_NODES
            ]
            for f in futures:
                f.result()
        print(f"\n{Colors.GREEN}{Colors.BOLD}[✓] Audit Finished! Detailed logs saved in: {LOGS_DIR}{Colors.ENDC}\n")

if __name__ == "__main__":
    main()
