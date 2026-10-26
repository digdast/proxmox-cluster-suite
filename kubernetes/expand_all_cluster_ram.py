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
    return out

def run_vm(ssh, vm_ip, cmd):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -i {SSH_KEY_PATH} root@{vm_ip} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    return out

def main():
    print("=" * 75)
    print("  EXPANDING RAM ACROSS ALL CLUSTER NODES BY +2GB (TOTAL 6GB PER NODE)")
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

        # 1. Check current guest memory
        guest_mem = run_vm(ssh, ip, "free -m | grep Mem:")
        parts = guest_mem.split()
        curr_total = int(parts[1]) if len(parts) > 1 else 0

        if curr_total >= 5800:
            ok(f"  {name} is already reporting 6GB RAM ({curr_total} MB). Setting hotplug...")
            if node == "pve-00":
                run_pve(ssh, f"qm set {vmid} -hotplug disk,network,usb,memory")
            else:
                run_pve(ssh, f"ssh -o StrictHostKeyChecking=no {node} qm set {vmid} -hotplug disk,network,usb,memory")
        else:
            log(f"  Current RAM: {curr_total} MB. Updating to 6144 MB and restarting VM...")
            
            # Set memory and hotplug in Proxmox
            if node == "pve-00":
                run_pve(ssh, f"qm set {vmid} -memory 6144 -hotplug disk,network,usb,memory")
                run_pve(ssh, f"qm shutdown {vmid}; qm wait {vmid}; qm start {vmid}")
            else:
                remote_cmd = f"qm set {vmid} -memory 6144 -hotplug disk,network,usb,memory; qm shutdown {vmid}; qm wait {vmid}; qm start {vmid}"
                run_pve(ssh, f"ssh -o StrictHostKeyChecking=no {node} '{remote_cmd}'")
            
            # Wait for VM to boot up and K3s to be Ready
            log(f"  Waiting for {name} ({ip}) to reboot and rejoin cluster...")
            time.sleep(12)
            for attempt in range(20):
                try:
                    check_mem = run_vm(ssh, ip, "free -m | grep Mem:")
                    if "Mem:" in check_mem:
                        p_check = check_mem.split()
                        new_total = int(p_check[1])
                        if new_total >= 5800:
                            ok(f"  {name} is back online with {new_total} MB RAM (6.0 GB)!")
                            break
                except Exception:
                    pass
                time.sleep(3)

        # Confirm K3s node is Ready
        node_status = run_vm(ssh, "192.168.0.81", f"export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; kubectl get node {name} --no-headers")
        status_word = "Ready" if "Ready" in node_status else "NotReady"
        ok(f"  Kubernetes Node Status: {name} is {status_word}!\n")

        # Record final stats
        final_mem_line = run_vm(ssh, ip, "free -m | grep Mem:")
        f_parts = final_mem_line.split()
        total_mb = f_parts[1] if len(f_parts) > 1 else "Unknown"
        avail_mb = f_parts[6] if len(f_parts) > 6 else "Unknown"
        results.append({
            "vmid": vmid,
            "name": name,
            "role": role,
            "node": node,
            "ip": ip,
            "total": f"{total_mb} MB",
            "avail": f"{avail_mb} MB",
            "k8s": status_word
        })

    ssh.close()

    print("=" * 75)
    print("  🎉 RAM EXPANSION (+2GB) COMPLETE ACROSS ALL CLUSTER NODES!")
    print("=" * 75)
    print(f"{'VMID':<6} {'Node Name':<16} {'Role':<15} {'Host':<8} {'IP Address':<15} {'Total RAM':<12} {'Available':<12} {'K8s'}")
    print("-" * 75)
    for r in results:
        print(f"{r['vmid']:<6} {r['name']:<16} {r['role']:<15} {r['node']:<8} {r['ip']:<15} {r['total']:<12} {r['avail']:<12} {r['k8s']}")
    print("=" * 75)

if __name__ == "__main__":
    main()
