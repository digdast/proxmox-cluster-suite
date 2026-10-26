import sys
import time
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
SSH_KEY_PATH = "/root/.ssh/id_rsa"
VM_USER = "plexadmin"

NODES = [
    {"name": "k8s-cp-01", "ip": "192.168.0.81", "role": "Control Plane 1"},
    {"name": "k8s-cp-02", "ip": "192.168.0.82", "role": "Control Plane 2"},
    {"name": "k8s-worker-01", "ip": "192.168.0.83", "role": "Worker 1"},
    {"name": "k8s-worker-02", "ip": "192.168.0.84", "role": "Worker 2"},
    {"name": "k8s-worker-03", "ip": "192.168.0.85", "role": "Worker 3"},
    {"name": "k8s-worker-04", "ip": "192.168.0.86", "role": "Worker 4"},
]

NFS_SERVER = "192.168.0.3"
NFS_SHARE = "/mnt/user/data"
MOUNT_POINT = "/data"
FSTAB_LINE = f"{NFS_SERVER}:{NFS_SHARE} {MOUNT_POINT} nfs _netdev,defaults,nofail 0 0"

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def run_vm(ssh, ip, cmd, timeout=120):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i {SSH_KEY_PATH} {VM_USER}@{ip} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  MOUNTING UNRAID NFS SHARE ON ALL KUBERNETES NODES")
    print(f"  Share: {NFS_SERVER}:{NFS_SHARE} -> {MOUNT_POINT}")
    print("  Target Nodes: 2 Control Planes, 4 Workers")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    results = []

    for node in NODES:
        name = node["name"]
        ip = node["ip"]
        role = node["role"]
        print(f"\n--- Configuring {name} ({role} @ {ip}) ---")

        # 1. Install nfs-common
        log(f"Ensuring nfs-common is installed on {name}...")
        install_cmd = (
            "export DEBIAN_FRONTEND=noninteractive && "
            "which mount.nfs || (sudo apt-get update -qq && sudo apt-get install -y -qq nfs-common)"
        )
        out_inst, er_inst = run_vm(ssh, ip, install_cmd, timeout=180)
        ok(f"nfs-common verified on {name}.")

        # 2. Create mount point
        log(f"Ensuring {MOUNT_POINT} directory exists...")
        run_vm(ssh, ip, f"sudo mkdir -p {MOUNT_POINT}")

        # 3. Add to /etc/fstab if not present
        log(f"Configuring persistent mount in /etc/fstab...")
        fstab_check = f"grep -q '{NFS_SHARE}' /etc/fstab || echo '{FSTAB_LINE}' | sudo tee -a /etc/fstab"
        run_vm(ssh, ip, fstab_check)

        # 4. Mount
        log(f"Mounting {MOUNT_POINT}...")
        run_vm(ssh, ip, f"sudo systemctl daemon-reload && sudo mount {MOUNT_POINT} || true")

        # 5. Verify mount
        df_out, _ = run_vm(ssh, ip, f"df -h {MOUNT_POINT}")
        lines = df_out.splitlines()
        mount_info = lines[-1] if len(lines) > 1 else df_out

        if NFS_SHARE in mount_info or NFS_SERVER in mount_info:
            ok(f"Successfully mounted on {name}: {mount_info}")
            results.append({"name": name, "ip": ip, "status": "Mounted", "details": mount_info})
        else:
            err(f"Mount verification warning on {name}: {df_out}")
            results.append({"name": name, "ip": ip, "status": "Failed", "details": df_out})

    ssh.close()

    print("\n" + "=" * 75)
    print("  MOUNT SUMMARY TABLE")
    print("=" * 75)
    print(f"{'Node Name':<16} {'IP Address':<15} {'Status':<10} {'Filesystem Info'}")
    print("-" * 75)
    for r in results:
        print(f"{r['name']:<16} {r['ip']:<15} {r['status']:<10} {r['details']}")
    print("=" * 75)

if __name__ == "__main__":
    main()
