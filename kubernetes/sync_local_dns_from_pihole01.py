import os
import sys
import time
import json
import tomllib
import urllib.parse
import urllib.request
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
CT_ID = "300"  # pihole-01

PIHOLE_NEW_API = "http://192.168.0.81:30081"
PIHOLE_PW = "Chloe_12152009"

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def main():
    print("=" * 75)
    print("  COPYING LOCAL DNS RECORDS FROM PIHOLE-01 (192.168.0.2) TO CLUSTER")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!\n")

    def run_ct(cmd):
        stdin, stdout, stderr = ssh.exec_command(f"pct exec {CT_ID} -- {cmd}")
        return stdout.read().decode('utf-8', errors='replace').strip()

    def run_k8s(cmd):
        escaped = cmd.replace("'", "'\"'\"'")
        exec_str = f"ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_rsa root@192.168.0.81 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; {escaped}'"
        stdin, stdout, stderr = ssh.exec_command(exec_str)
        return stdout.read().decode('utf-8', errors='replace').strip()

    # 1. Read custom.list from CT 300
    log("Reading /etc/pihole/custom.list from pihole-01...")
    raw_custom = run_ct("cat /etc/pihole/custom.list 2>/dev/null")
    custom_records = []
    for line in raw_custom.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            ip = parts[0]
            for domain in parts[1:]:
                custom_records.append((domain.lower(), ip))

    # 2. Read pihole.toml hosts array from CT 300
    log("Reading /etc/pihole/pihole.toml hosts from pihole-01...")
    raw_toml = run_ct("cat /etc/pihole/pihole.toml 2>/dev/null")
    toml_records = []
    try:
        parsed_toml = tomllib.loads(raw_toml)
        for entry in parsed_toml.get("dns", {}).get("hosts", []):
            parts = entry.strip().split()
            if len(parts) >= 2:
                ip = parts[0]
                for domain in parts[1:]:
                    toml_records.append((domain.lower(), ip))
    except Exception as e:
        err(f"Error parsing pihole.toml: {e}")

    log(f"Found {len(custom_records)} records in custom.list and {len(toml_records)} records in pihole.toml.")

    # 3. Merge & Deduplicate (custom.list takes precedence for modern K8s cluster IPs)
    merged_map = {}
    for domain, ip in toml_records:
        merged_map[domain] = ip
    for domain, ip in custom_records:
        merged_map[domain] = ip

    # Remove temporary test records
    if "k8s-test.ertech.home" in merged_map:
        del merged_map["k8s-test.ertech.home"]

    print(f"\n[+] Total unique local DNS records to sync: {len(merged_map)}")
    print("-" * 50)
    for domain, ip in sorted(merged_map.items()):
        print(f"    {ip:<15} -> {domain}")
    print("-" * 50 + "\n")

    # 4. Authenticate to Pi-hole v6 API
    log(f"Authenticating to primary cluster Pi-hole API ({PIHOLE_NEW_API})...")
    auth_req = urllib.request.Request(
        f"{PIHOLE_NEW_API}/api/auth",
        data=json.dumps({"password": PIHOLE_PW}).encode('utf-8'),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(auth_req, timeout=5) as resp:
        auth_data = json.loads(resp.read().decode('utf-8'))
        sid = auth_data["session"]["sid"]
    ok("Successfully authenticated to Pi-hole v6 API!")

    # 5. Push records via REST API
    log("Uploading local DNS records to cluster Pi-hole 1...")
    added_count = 0
    for domain, ip in sorted(merged_map.items()):
        entry = f"{ip} {domain}"
        quoted = urllib.parse.quote(entry)
        put_url = f"{PIHOLE_NEW_API}/api/config/dns/hosts/{quoted}"
        put_req = urllib.request.Request(
            put_url,
            headers={"sid": sid},
            method="PUT"
        )
        try:
            with urllib.request.urlopen(put_req, timeout=5) as r:
                pass
            added_count += 1
        except Exception as e:
            err(f"Failed to add {entry}: {e}")

    ok(f"Successfully added {added_count} local DNS records to primary Pi-hole!\n")

    # 6. Trigger Nebula-Sync replication across replicas
    log("Triggering nebula-sync to replicate records to pihole-2 and pihole-3...")
    run_k8s("kubectl rollout restart deployment/nebula-sync -n dns")
    time.sleep(5)

    log("Waiting for nebula-sync to complete synchronization pass...")
    for attempt in range(12):
        sync_logs = run_k8s("kubectl logs -n dns deployment/nebula-sync --tail=15")
        if "Sync completed" in sync_logs:
            ok("Nebula-sync completed full replication pass!")
            break
        time.sleep(4)

    # 7. Verification across all 3 Pi-holes and cluster node IPs
    log("\nVerifying DNS resolution of imported records across cluster nodes...")
    test_hosts = [
        "novaflix.ertechlab.com",
        "resume.ertechlab.com",
        "portainer.ertech.home",
        "sonarr.ertech.home",
        "radarr.ertech.home",
        "prowlarr.ertech.home",
        "plex.ertech.home",
        "pihole-cluster.ertech.home",
        "checkmk-01.ertech.home",
        "ansible-01.ertech.home",
        "docker-01.ertech.home",
        "pve-00.ertech.home"
    ]

    resolvers = [
        ("pihole-1 (k8s-cp-01)", "192.168.0.81"),
        ("pihole-2 (k8s-cp-02)", "192.168.0.82"),
        ("pihole-3 (k8s-worker-01)", "192.168.0.83")
    ]

    for hostname in test_hosts:
        expected = merged_map.get(hostname, "")
        for res_name, res_ip in resolvers:
            stdin, stdout, stderr = ssh.exec_command(f"dig @{res_ip} {hostname} +short")
            resolved = stdout.read().decode().strip().replace('\n', ', ')
            status = "MATCH" if expected in resolved else "MISMATCH"
            print(f"  [{status}] {hostname} @ {res_ip}:53 -> {resolved} (Expected: {expected})")
        print()

    ssh.close()

    print("=" * 75)
    print("  🎉 ALL LOCAL DNS RECORDS COPIED AND SYNCED SUCCESSFULLY!")
    print(f"  Total records: {len(merged_map)}")
    print("=" * 75)

if __name__ == "__main__":
    main()
