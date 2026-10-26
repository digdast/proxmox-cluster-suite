import sys
import json
import urllib.request
import paramiko
import time

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.0.30', username='root', password='sone_420')

def r(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

print("=== 1. Checking nebula-sync replication status ===")
# Wait a moment for nebula-sync pod to cycle and log
sync_pod = r("ssh -o StrictHostKeyChecking=no 192.168.0.81 'kubectl get pods -n dns -l app.kubernetes.io/name=nebula-sync -o jsonpath=\"{.items[0].metadata.name}\"'")
print(f"Sync pod name: {sync_pod}")

for _ in range(6):
    pod_status = r(f"ssh -o StrictHostKeyChecking=no 192.168.0.81 'kubectl get pod {sync_pod} -n dns -o jsonpath=\"{{.status.phase}}\"'")
    if pod_status == "Running":
        break
    time.sleep(3)

sync_logs = r(f"ssh -o StrictHostKeyChecking=no 192.168.0.81 'kubectl logs {sync_pod} -n dns --tail=30'")
print(f"Sync logs:\n{sync_logs}\n")

print("=== 2. Checking total custom hosts in Pi-hole 1, 2, and 3 via API ===")
def get_hosts_count(ip, port):
    try:
        login_url = f"http://{ip}:{port}/api/auth"
        req = urllib.request.Request(
            login_url,
            data=json.dumps({"password": "Chloe_12152009"}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            sid = json.loads(resp.read().decode('utf-8'))['session']['sid']
        
        url = f"http://{ip}:{port}/api/config/dns/hosts"
        req2 = urllib.request.Request(url, headers={"sid": sid})
        with urllib.request.urlopen(req2, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return len(data.get("config", {}).get("dns", {}).get("hosts", []))
    except Exception as e:
        return f"Error: {e}"

print(f"Pi-hole 1 (192.168.0.81:30081): {get_hosts_count('192.168.0.81', 30081)} hosts")
print(f"Pi-hole 2 (192.168.0.82:30082): {get_hosts_count('192.168.0.82', 30082)} hosts")
print(f"Pi-hole 3 (192.168.0.83:30083): {get_hosts_count('192.168.0.83', 30083)} hosts")

print("\n=== 3. DNS Resolution Verification on all 3 Pi-hole Resolvers ===")
test_queries = [
    # Hypervisors
    ("pve-00", "192.168.0.30"),
    ("pve-00.ertech.home", "192.168.0.30"),
    ("pve-01", "192.168.0.31"),
    ("pve-02", "192.168.0.32"),
    ("pve-03", "192.168.0.33"),
    ("pve-04", "192.168.0.34"),
    ("pve-cluster-01", "192.168.0.30"),
    ("pve-cluster.ertech.home", "192.168.0.30"),
    ("pve.ertech.home", "192.168.0.30"),
    ("pve-00-cluster", "192.168.0.130"),
    ("nas-01", "192.168.0.3"),
    ("router", "192.168.0.1"),
    # VMs
    ("k8s-worker-00", "192.168.0.66"),
    ("k8s-cp-01", "192.168.0.81"),
    ("k8s-worker-04", "192.168.0.86"),
    # LXCs
    ("ansible-01", "192.168.0.10"),
    ("cloudflare-ddns", "192.168.0.246"),
    ("zoraxy.ertech.home", "192.168.0.40"),
    ("rustdeskserver.ertech.home", "192.168.0.16"),
    ("authentik.ertech.home", "192.168.0.15"),
    ("resume.ertech.home", "192.168.0.12"),
    ("pihole-01.ertech.home", "192.168.0.2"),
    ("aegisdns-01.ertech.home", "192.168.0.53"),
    ("checkmk-01.ertech.home", "192.168.0.51"),
    ("reconya-01.ertech.home", "192.168.0.54"),
    ("sonarr-01.ertech.home", "192.168.0.70"),
    ("radarr-01.ertech.home", "192.168.0.71"),
    ("prowlarr-01.ertech.home", "192.168.0.72"),
    ("plexserver-01.ertech.home", "192.168.0.75"),
    ("qbittorrent-01.ertech.home", "192.168.0.74"),
    ("novaflix-01.ertech.home", "192.168.0.76"),
    ("it-tools.ertech.home", "192.168.0.27"),
    ("apache-tomcat-01.ertech.home", "192.168.0.39")
]

resolvers = ["192.168.0.81", "192.168.0.82", "192.168.0.83"]

all_passed = True
for domain, expected_ip in test_queries:
    results = []
    for r_ip in resolvers:
        ans = r(f"dig +short @{r_ip} {domain}").strip()
        results.append(ans)
    
    status = "OK" if all(a == expected_ip for a in results) else "FAIL"
    if status == "FAIL":
        all_passed = False
    print(f"[{status}] {domain:<30} -> Expected: {expected_ip:<15} | Results: {results}")

print(f"\nFinal verification: {'ALL TESTS PASSED!' if all_passed else 'SOME TESTS FAILED'}")

ssh.close()
