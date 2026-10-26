import os
import sys
import time
import json
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
SSH_KEY_PATH = "/root/.ssh/id_rsa"
VM_USER = "plexadmin"
K3S_TOKEN = "k3s-secret-token-ertechlab-2026-sovereign-ha"

NODES = [
    {"vmid": 3010, "name": "k8s-cp-01", "node": "pve-00", "role": "control-plane", "ip": "192.168.0.81"},
    {"vmid": 3011, "name": "k8s-cp-02", "node": "pve-04", "role": "control-plane", "ip": "192.168.0.82"},
    {"vmid": 3020, "name": "k8s-worker-01", "node": "pve-01", "role": "worker", "ip": "192.168.0.83"},
    {"vmid": 3030, "name": "k8s-worker-02", "node": "pve-02", "role": "worker", "ip": "192.168.0.84"},
    {"vmid": 3040, "name": "k8s-worker-03", "node": "pve-03", "role": "worker", "ip": "192.168.0.85"},
    {"vmid": 3050, "name": "k8s-worker-04", "node": "pve-04", "role": "worker", "ip": "192.168.0.86"},
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

def run_vm(ssh, vm_ip, cmd, timeout=120):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i {SSH_KEY_PATH} {VM_USER}@{vm_ip} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  PROXMOX VE: KUBERNETES HIGH AVAILABILITY CLUSTER INSTALLATION")
    print("  Control Planes: k8s-cp-01 (192.168.0.81), k8s-cp-02 (192.168.0.82)")
    print("  Workers: k8s-worker-01..04 (192.168.0.83 - 192.168.0.86)")
    print("  Storage: Expanded +20GB (Total 22-24GB per node)")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    # Verify all VMs are reachable and have internet connectivity
    log("Verifying SSH and outbound internet connectivity on all 6 nodes...")
    for n in NODES:
        ip = n["ip"]
        name = n["name"]
        out, _ = run_vm(ssh, ip, "curl -s -o /dev/null -w '%{http_code}' https://get.k3s.io")
        if "200" in out or "301" in out or "302" in out:
            ok(f"{name} ({ip}) is online and has internet access to get.k3s.io (HTTP {out})")
        else:
            err(f"{name} ({ip}) response: {out} (checking DNS/gateway)")

    # 1. Initialize Control Plane 1
    cp1 = NODES[0]
    log(f"\n--- Initializing Control Plane 1 on {cp1['name']} ({cp1['ip']}) ---")
    cp1_install = (
        f"curl -sfL https://get.k3s.io | sudo sh -s - server "
        f"--cluster-init "
        f"--tls-san {NODES[0]['ip']} "
        f"--tls-san {NODES[1]['ip']} "
        f"--tls-san k8s.ertech.home "
        f"--tls-san 136.56.3.230 "
        f"--node-ip {cp1['ip']} "
        f"--token {K3S_TOKEN} "
        f"--write-kubeconfig-mode 644"
    )
    log("Executing K3s server --cluster-init...")
    out, er = run_vm(ssh, cp1['ip'], cp1_install, timeout=180)
    if out:
        print(f"  CP1 stdout: {out[-300:]}")
    if er:
        print(f"  CP1 stderr: {er[-300:]}")

    # Wait for CP1 K3s to be active
    log("Waiting for k3s.service on k8s-cp-01 to be active...")
    for _ in range(20):
        status, _ = run_vm(ssh, cp1['ip'], "sudo systemctl is-active k3s")
        if status.strip() == "active":
            ok("k3s.service is ACTIVE on k8s-cp-01!")
            break
        time.sleep(3)

    nodes_out, _ = run_vm(ssh, cp1['ip'], "sudo kubectl get nodes")
    print(f"Nodes status on CP1:\n{nodes_out}")

    # 2. Join Control Plane 2
    cp2 = NODES[1]
    log(f"\n--- Joining Control Plane 2 on {cp2['name']} ({cp2['ip']}) to etcd cluster ---")
    cp2_install = (
        f"curl -sfL https://get.k3s.io | sudo sh -s - server "
        f"--server https://{cp1['ip']}:6443 "
        f"--tls-san {NODES[0]['ip']} "
        f"--tls-san {NODES[1]['ip']} "
        f"--tls-san k8s.ertech.home "
        f"--tls-san 136.56.3.230 "
        f"--node-ip {cp2['ip']} "
        f"--token {K3S_TOKEN} "
        f"--write-kubeconfig-mode 644"
    )
    log("Executing K3s server join on CP2...")
    out, er = run_vm(ssh, cp2['ip'], cp2_install, timeout=180)
    if out:
        print(f"  CP2 stdout: {out[-300:]}")
    if er:
        print(f"  CP2 stderr: {er[-300:]}")

    # Wait for CP2 K3s to be active
    log("Waiting for k3s.service on k8s-cp-02 to be active...")
    for _ in range(25):
        status, _ = run_vm(ssh, cp2['ip'], "sudo systemctl is-active k3s")
        if status.strip() == "active":
            ok("k3s.service is ACTIVE on k8s-cp-02!")
            break
        time.sleep(3)

    # 3. Join Workers 1 through 4
    for w in NODES[2:]:
        log(f"\n--- Joining Worker {w['name']} ({w['ip']}) ---")
        w_install = (
            f"curl -sfL https://get.k3s.io | sudo K3S_URL=https://{cp1['ip']}:6443 "
            f"K3S_TOKEN={K3S_TOKEN} "
            f"sh -s - agent --node-ip {w['ip']}"
        )
        out, er = run_vm(ssh, w['ip'], w_install, timeout=180)
        if out:
            print(f"  {w['name']} stdout: {out[-200:]}")
        
        # Verify k3s-agent.service
        for _ in range(20):
            st, _ = run_vm(ssh, w['ip'], "sudo systemctl is-active k3s-agent")
            if st.strip() == "active":
                ok(f"k3s-agent.service is ACTIVE on {w['name']}!")
                break
            time.sleep(2)

    # 4. Verify all nodes in cluster
    log("\nWaiting for all 6 nodes to report Ready status...")
    time.sleep(10)
    nodes_final, _ = run_vm(ssh, cp1['ip'], "sudo kubectl get nodes -o wide")
    print("\n" + "=" * 80)
    print("  KUBERNETES CLUSTER STATUS (kubectl get nodes -o wide)")
    print("=" * 80)
    print(nodes_final)
    print("=" * 80)

    # 5. Label worker nodes
    for w in NODES[2:]:
        run_vm(ssh, cp1['ip'], f"sudo kubectl label node {w['name']} node-role.kubernetes.io/worker=worker --overwrite")
    ok("Labeled worker nodes with node-role.kubernetes.io/worker=worker")

    # 6. Export Kubeconfig
    log("\nFetching cluster kubeconfig...")
    kubeconfig_raw, _ = run_vm(ssh, cp1['ip'], "sudo cat /etc/rancher/k3s/k3s.yaml")
    if kubeconfig_raw:
        kubeconfig_ext = kubeconfig_raw.replace("127.0.0.1", cp1['ip'])
        
        # Save to Windows host
        local_path = r"C:\scripts\k8s-kubeconfig.yaml"
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(kubeconfig_ext)
        ok(f"Kubeconfig saved locally to: {local_path}")

        # Save to pve-00
        run_pve(ssh, "mkdir -p /root/.kube")
        sftp = ssh.open_sftp()
        with sftp.open("/root/.kube/config", "w") as f:
            f.write(kubeconfig_ext)
        sftp.close()
        run_pve(ssh, "chmod 600 /root/.kube/config")
        ok("Kubeconfig saved to pve-00:/root/.kube/config")

    # 7. Update Pi-hole DNS
    log("\nUpdating Pi-hole DNS (192.168.0.2) with new cluster hostnames...")
    dns_script = """pct exec 300 -- python3 -c '
hosts_to_add = [
    ("192.168.0.81", "k8s-cp-01.ertech.home"),
    ("192.168.0.82", "k8s-cp-02.ertech.home"),
    ("192.168.0.83", "k8s-worker-01.ertech.home"),
    ("192.168.0.84", "k8s-worker-02.ertech.home"),
    ("192.168.0.85", "k8s-worker-03.ertech.home"),
    ("192.168.0.86", "k8s-worker-04.ertech.home"),
    ("192.168.0.81", "k8s.ertech.home")
]

with open("/etc/pihole/custom.list", "a+") as f:
    f.seek(0)
    existing = f.read()
    for ip, domain in hosts_to_add:
        line = f"{ip} {domain}"
        if domain not in existing:
            f.write(f"\\n{line}")
            print(f"Added: {line}")
        else:
            print(f"Already exists: {domain}")
'"""
    out_dns, _ = run_pve(ssh, dns_script)
    print(out_dns)
    run_pve(ssh, "pct exec 300 -- systemctl restart pihole-FTL")
    ok("Pi-hole DNS reloaded with cluster domain names!")

    # 8. Check cluster pods and components
    pods_out, _ = run_vm(ssh, cp1['ip'], "sudo kubectl get pods -A -o wide")
    print("\n" + "=" * 80)
    print("  KUBERNETES CLUSTER SYSTEM PODS (kubectl get pods -A -o wide)")
    print("=" * 80)
    print(pods_out)
    print("=" * 80)

    ssh.close()
    ok("\nKubernetes cluster deployment completed successfully!")

if __name__ == "__main__":
    main()
