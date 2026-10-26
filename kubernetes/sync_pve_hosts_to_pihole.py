import sys
import json
import urllib.request
import urllib.parse
import time
import subprocess
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

# 1. Authenticate with Pi-hole 1
def get_sid(base_url="http://192.168.0.81:30081"):
    login_url = f"{base_url}/api/auth"
    req = urllib.request.Request(
        login_url,
        data=json.dumps({"password": "Chloe_12152009"}).encode('utf-8'),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))['session']['sid']

sid = get_sid()

# 2. Get existing hosts
def get_hosts(sid, base_url="http://192.168.0.81:30081"):
    url = f"{base_url}/api/config/dns/hosts"
    req = urllib.request.Request(url, headers={"sid": sid})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data.get("config", {}).get("dns", {}).get("hosts", [])

current_hosts = get_hosts(sid)
print(f"Current Pi-hole hosts count: {len(current_hosts)}")

# 3. Delete helper
def delete_host(ip, domain, sid, base_url="http://192.168.0.81:30081"):
    encoded = urllib.parse.quote(f"{ip} {domain}")
    url = f"{base_url}/api/config/dns/hosts/{encoded}"
    req = urllib.request.Request(url, method='DELETE', headers={"sid": sid})
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Deleted old host: {ip} {domain} -> {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Could not delete {ip} {domain}: {e.code}")
        return False

# If 192.168.0.8 pihole-01.ertech.home exists, delete it so 192.168.0.2 can have it
if "192.168.0.8 pihole-01.ertech.home" in current_hosts:
    delete_host("192.168.0.8", "pihole-01.ertech.home", sid)

# 4. Add helper
def add_host(ip, domain, sid, base_url="http://192.168.0.81:30081"):
    encoded = urllib.parse.quote(f"{ip} {domain}")
    url = f"{base_url}/api/config/dns/hosts/{encoded}"
    req = urllib.request.Request(url, method='PUT', headers={"sid": sid})
    try:
        with urllib.request.urlopen(req) as resp:
            return "added"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='ignore')
        if "item_already_present" in err_body:
            return "exists"
        else:
            print(f"Error {e.code} adding {ip} {domain}: {err_body}")
            return f"error_{e.code}"

# Define the complete desired PVE cluster hosts
records_to_sync = [
    # 1. PVE Hypervisor Nodes (Management network vmbr0)
    ("192.168.0.30", "pve-00.ertech.home"),
    ("192.168.0.30", "pve-00"),
    ("192.168.0.31", "pve-01.ertech.home"),
    ("192.168.0.31", "pve-01"),
    ("192.168.0.32", "pve-02.ertech.home"),
    ("192.168.0.32", "pve-02"),
    ("192.168.0.33", "pve-03.ertech.home"),
    ("192.168.0.33", "pve-03"),
    ("192.168.0.34", "pve-04.ertech.home"),
    ("192.168.0.34", "pve-04"),

    # 2. PVE Cluster Hostnames & Aliases (Management network vmbr0)
    ("192.168.0.30", "pve-cluster-01.ertech.home"),
    ("192.168.0.30", "pve-cluster-01"),
    ("192.168.0.30", "pve-clust-01.ertech.home"),
    ("192.168.0.30", "pve-clust-01"),
    ("192.168.0.30", "pve-cluster.ertech.home"),
    ("192.168.0.30", "pve-cluster"),
    ("192.168.0.30", "pve.ertech.home"),
    ("192.168.0.30", "pve"),

    # 3. PVE Cluster Private / Storage Network (vmbr1)
    ("192.168.0.130", "pve-00-cluster.ertech.home"),
    ("192.168.0.130", "pve-00-cluster"),
    ("192.168.0.131", "pve-01-cluster.ertech.home"),
    ("192.168.0.131", "pve-01-cluster"),
    ("192.168.0.132", "pve-02-cluster.ertech.home"),
    ("192.168.0.132", "pve-02-cluster"),
    ("192.168.0.133", "pve-03-cluster.ertech.home"),
    ("192.168.0.133", "pve-03-cluster"),
    ("192.168.0.134", "pve-04-cluster.ertech.home"),
    ("192.168.0.134", "pve-04-cluster"),

    # 4. PVE NFS Storage Host
    ("192.168.0.3", "nas-01.ertech.home"),
    ("192.168.0.3", "nas-01"),

    # 5. Network Gateway / Router
    ("192.168.0.1", "router.ertech.home"),
    ("192.168.0.1", "router"),
    ("192.168.0.1", "gateway.ertech.home"),
    ("192.168.0.1", "gateway"),

    # 6. PVE Virtual Machines (QEMU Guests)
    ("192.168.0.66", "k8s-worker-00.ertech.home"),
    ("192.168.0.66", "k8s-worker-00"),
    ("192.168.0.81", "k8s-cp-01.ertech.home"),
    ("192.168.0.81", "k8s-cp-01"),
    ("192.168.0.82", "k8s-cp-02.ertech.home"),
    ("192.168.0.82", "k8s-cp-02"),
    ("192.168.0.83", "k8s-worker-01.ertech.home"),
    ("192.168.0.83", "k8s-worker-01"),
    ("192.168.0.84", "k8s-worker-02.ertech.home"),
    ("192.168.0.84", "k8s-worker-02"),
    ("192.168.0.85", "k8s-worker-03.ertech.home"),
    ("192.168.0.85", "k8s-worker-03"),
    ("192.168.0.86", "k8s-worker-04.ertech.home"),
    ("192.168.0.86", "k8s-worker-04"),

    # 7. PVE LXC Containers
    # CT 100: ansible-01
    ("192.168.0.10", "ansible-01.ertech.home"),
    ("192.168.0.10", "ansible-01"),
    ("192.168.0.10", "ansible.ertech.home"),
    ("192.168.0.10", "ansible"),

    # CT 103: cloudflare-ddns
    ("192.168.0.246", "cloudflare-ddns.ertech.home"),
    ("192.168.0.246", "cloudflare-ddns"),
    ("192.168.0.246", "ddns.ertech.home"),
    ("192.168.0.246", "ddns"),

    # CT 104: zoraxy
    ("192.168.0.40", "zoraxy.ertech.home"),
    ("192.168.0.40", "zoraxy"),

    # CT 105: rustdeskserver
    ("192.168.0.16", "rustdeskserver.ertech.home"),
    ("192.168.0.16", "rustdeskserver"),
    ("192.168.0.16", "rustdesk.ertech.home"),
    ("192.168.0.16", "rustdesk"),

    # CT 106: support
    ("192.168.0.19", "support.ertechlab.com"),
    ("192.168.0.19", "support.ertech.home"),
    ("192.168.0.19", "support"),

    # CT 109: authentik
    ("192.168.0.15", "authentik.ertech.home"),
    ("192.168.0.15", "authentik"),
    ("192.168.0.15", "auth.ertech.home"),
    ("192.168.0.15", "auth"),

    # CT 110: resume
    ("192.168.0.12", "resume.ertech.home"),
    ("192.168.0.12", "resume"),
    ("192.168.0.12", "resume-01.ertech.home"),
    ("192.168.0.12", "resume-01"),

    # CT 200: npm-01
    ("192.168.0.8", "npm-01.ertech.home"),
    ("192.168.0.8", "npm-01"),
    ("192.168.0.8", "npm.ertech.home"),
    ("192.168.0.8", "npm"),

    # CT 201: flaresolver-01
    ("192.168.0.21", "flaresolver-01.ertech.home"),
    ("192.168.0.21", "flaresolver-01"),
    ("192.168.0.21", "flaresolver.ertech.home"),
    ("192.168.0.21", "flaresolver"),

    # CT 300: pihole-01 (legacy CT)
    ("192.168.0.2", "pihole-01.ertech.home"),
    ("192.168.0.2", "pihole-01"),
    ("192.168.0.2", "legacy-pihole.ertech.home"),
    ("192.168.0.2", "legacy-pihole"),

    # CT 353: aegisdns-01
    ("192.168.0.53", "aegisdns-01.ertech.home"),
    ("192.168.0.53", "aegisdns-01"),
    ("192.168.0.53", "aegisdns.ertech.home"),
    ("192.168.0.53", "aegisdns"),

    # CT 501: checkmk-01
    ("192.168.0.51", "checkmk-01.ertech.home"),
    ("192.168.0.51", "checkmk-01"),
    ("192.168.0.51", "checkmk.ertech.home"),
    ("192.168.0.51", "checkmk"),

    # CT 504: reconya-01
    ("192.168.0.54", "reconya-01.ertech.home"),
    ("192.168.0.54", "reconya-01"),
    ("192.168.0.54", "reconya.ertech.home"),
    ("192.168.0.54", "reconya"),

    # CT 700: sonarr-01
    ("192.168.0.70", "sonarr-01.ertech.home"),
    ("192.168.0.70", "sonarr-01"),

    # CT 701: radarr-01
    ("192.168.0.71", "radarr-01.ertech.home"),
    ("192.168.0.71", "radarr-01"),

    # CT 702: prowlarr-01
    ("192.168.0.72", "prowlarr-01.ertech.home"),
    ("192.168.0.72", "prowlarr-01"),

    # CT 703: plexserver-01
    ("192.168.0.75", "plexserver-01.ertech.home"),
    ("192.168.0.75", "plexserver-01"),
    ("192.168.0.75", "plex-01.ertech.home"),
    ("192.168.0.75", "plex-01"),

    # CT 704: qbittorrent-01
    ("192.168.0.74", "qbittorrent-01.ertech.home"),
    ("192.168.0.74", "qbittorrent-01"),
    ("192.168.0.74", "qbittorrent.ertech.home"),
    ("192.168.0.74", "qbittorrent"),

    # CT 705: novaflix-01
    ("192.168.0.76", "novaflix-01.ertech.home"),
    ("192.168.0.76", "novaflix-01"),

    # CT 10001: alpine-it-tools
    ("192.168.0.27", "alpine-it-tools.ertech.home"),
    ("192.168.0.27", "alpine-it-tools"),
    ("192.168.0.27", "it-tools.ertech.home"),
    ("192.168.0.27", "it-tools"),

    # CT 20001: apache-tomcat-01
    ("192.168.0.39", "apache-tomcat-01.ertech.home"),
    ("192.168.0.39", "apache-tomcat-01"),
    ("192.168.0.39", "tomcat-01.ertech.home"),
    ("192.168.0.39", "tomcat-01")
]

added_count = 0
exists_count = 0
error_count = 0

print(f"\nProcessing {len(records_to_sync)} host records...")

for ip, domain in records_to_sync:
    status = add_host(ip, domain, sid)
    if status == "added":
        added_count += 1
        print(f" [+] Added: {ip:<15} -> {domain}")
    elif status == "exists":
        exists_count += 1
    else:
        error_count += 1

print(f"\nSync complete: {added_count} added, {exists_count} already existed, {error_count} errors.")

# 5. Trigger nebula-sync replication across Pi-hole cluster
print("\nTriggering nebula-sync replication...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.0.30', username='root', password='sone_420')

def r(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

print(r("ssh -o StrictHostKeyChecking=no 192.168.0.81 'kubectl rollout restart deployment/nebula-sync -n dns'"))
print("Waiting 10 seconds for sync propagation...")
time.sleep(10)

# Check nebula-sync logs
sync_logs = r("ssh -o StrictHostKeyChecking=no 192.168.0.81 'kubectl logs -n dns -l app.kubernetes.io/name=nebula-sync --tail=25'")
print("nebula-sync logs:")
print(sync_logs)

ssh.close()
