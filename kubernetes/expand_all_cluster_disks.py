import os
import sys
import time
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
SSH_KEY_PATH = "/root/.ssh/id_rsa"

NODES = [
    {"vmid": 3010, "name": "k8s-cp-01", "node": "pve-00", "role": "Control Plane", "ip": "192.168.0.81"},
    {"vmid": 3011, "name": "k8s-cp-02", "node": "pve-04", "role": "Control Plane", "ip": "192.168.0.82"},
    {"vmid": 3020, "name": "k8s-worker-01", "node": "pve-01", "role": "Worker", "ip": "192.168.0.83"},
    {"vmid": 3030, "name": "k8s-worker-02", "node": "pve-02", "role": "Worker", "ip": "192.168.0.84"},
    {"vmid": 3040, "name": "k8s-worker-03", "node": "pve-03", "role": "Worker", "ip": "192.168.0.85"},
    {"vmid": 3050, "name": "k8s-worker-04", "node": "pve-04", "role": "Worker", "ip": "192.168.0.86"},
]

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def run_pve(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def run_vm(ssh, vm_ip, cmd):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -i {SSH_KEY_PATH} root@{vm_ip} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  EXPANDING DISKS ACROSS ALL CONTROL PLANES & WORKERS BY +40GB")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!\n")

    results = []

    for item in NODES:
        vmid = item["vmid"]
        name = item["name"]
        node = item["node"]
        ip = item["ip"]
        role = item["role"]

        log(f"Processing VM {vmid} ({name} - {role}) on {node} [{ip}]...")

        # 1. Check current disk size in Proxmox
        if node == "pve-00":
            check_cmd = f"qm config {vmid} | grep scsi0"
        else:
            check_cmd = f"ssh -o StrictHostKeyChecking=no {node} qm config {vmid} | grep scsi0"
        
        cfg_out, _ = run_pve(ssh, check_cmd)
        
        # 2. Resize if not already ~65024M
        if "65024M" not in cfg_out and "size=64G" not in cfg_out:
            log(f"  Expanding virtual disk scsi0 by +40G on {node}...")
            if node == "pve-00":
                resize_cmd = f"qm resize {vmid} scsi0 +40G"
            else:
                resize_cmd = f"ssh -o StrictHostKeyChecking=no {node} qm resize {vmid} scsi0 +40G"
            
            res_out, res_err = run_pve(ssh, resize_cmd)
            if res_err and "error" in res_err.lower():
                err(f"  Resize error on VM {vmid}: {res_err}")
            else:
                ok(f"  Proxmox virtual disk expanded by +40G!")
        else:
            ok(f"  Proxmox virtual disk already expanded ({cfg_out})")

        # 3. Online Partition Grow & Filesystem Resize inside Guest OS
        log(f"  Expanding partition /dev/sda1 and ext4 filesystem inside {name}...")
        grow_cmd = "growpart /dev/sda 1 2>&1; resize2fs /dev/sda1 2>&1; df -h / | tail -n 1"
        grow_out, grow_err = run_vm(ssh, ip, grow_cmd)
        
        # 4. Get final filesystem status
        df_final, _ = run_vm(ssh, ip, "df -h / | tail -n 1")
        parts = df_final.split()
        size_str = parts[1] if len(parts) > 1 else "Unknown"
        used_str = parts[2] if len(parts) > 2 else "Unknown"
        avail_str = parts[3] if len(parts) > 3 else "Unknown"
        pct_str = parts[4] if len(parts) > 4 else "Unknown"

        ok(f"  {name} Root FS: Size={size_str}, Used={used_str}, Avail={avail_str} ({pct_str})\n")
        results.append({
            "vmid": vmid,
            "name": name,
            "role": role,
            "node": node,
            "ip": ip,
            "size": size_str,
            "used": used_str,
            "avail": avail_str,
            "pct": pct_str
        })

    ssh.close()

    print("=" * 75)
    print("  🎉 DISK EXPANSION (+40GB) COMPLETE ACROSS ALL NODES!")
    print("=" * 75)
    print(f"{'VMID':<6} {'Node Name':<16} {'Role':<15} {'Host':<8} {'IP Address':<15} {'Total':<8} {'Free':<8} {'Usage'}")
    print("-" * 75)
    for r in results:
        print(f"{r['vmid']:<6} {r['name']:<16} {r['role']:<15} {r['node']:<8} {r['ip']:<15} {r['size']:<8} {r['avail']:<8} {r['pct']}")
    print("=" * 75)

if __name__ == "__main__":
    main()
