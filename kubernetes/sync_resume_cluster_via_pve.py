import os
import sys
import tarfile
import paramiko
import urllib.request
import ssl

sys.stdout.reconfigure(encoding='utf-8')

LOCAL_SITE_DIR = r"C:\scripts\resume_ertechlab_deploy\site"
LOCAL_TAR = r"C:\scripts\resume_site_bundle.tar.gz"

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PW = "sone_420"

K8S_HOST = "192.168.0.81"
K8S_WEB_DIR = "/data/resume"

LIVE_URL = "https://resume.ertechlab.com"

def pack_site():
    print(f"[*] Packaging {LOCAL_SITE_DIR} into {LOCAL_TAR}...")
    with tarfile.open(LOCAL_TAR, "w:gz") as tar:
        for item in os.listdir(LOCAL_SITE_DIR):
            item_path = os.path.join(LOCAL_SITE_DIR, item)
            tar.add(item_path, arcname=item)
    print(f"[✓] Bundle created ({os.path.getsize(LOCAL_TAR):,} bytes)")

def deploy_via_pve():
    pack_site()
    
    print(f"\n[*] Connecting to PVE gateway ({PVE_HOST})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, username=PVE_USER, password=PVE_PW, timeout=10)
    print("[✓] Connected to PVE gateway.")

    sftp = ssh.open_sftp()
    remote_tar = "/tmp/resume_bundle.tar.gz"
    print(f"[*] SFTP uploading {LOCAL_TAR} -> {PVE_HOST}:{remote_tar}...")
    sftp.put(LOCAL_TAR, remote_tar)
    sftp.close()
    print("[✓] Uploaded to PVE gateway.")

    # Push from PVE to k8s host and extract
    print(f"\n[*] Streaming bundle from PVE to {K8S_HOST}:{K8S_WEB_DIR}...")
    remote_cmd = (
        f"scp -o StrictHostKeyChecking=no {remote_tar} root@{K8S_HOST}:/tmp/resume_bundle.tar.gz && "
        f"ssh -o StrictHostKeyChecking=no root@{K8S_HOST} "
        f"'mkdir -p {K8S_WEB_DIR} && tar --no-same-owner -xzf /tmp/resume_bundle.tar.gz -C {K8S_WEB_DIR} && chmod -R 755 {K8S_WEB_DIR} && rm /tmp/resume_bundle.tar.gz' && "
        f"rm -f {remote_tar}"
    )
    stdin, stdout, stderr = ssh.exec_command(remote_cmd)
    out = stdout.read().decode('utf-8')
    err = stderr.read().decode('utf-8')
    if out:
        print("STDOUT:", out)
    if err and "Warning: Permanently added" not in err:
        print("STDERR:", err)

    print("\n[*] Inspecting remote files on shared NFS storage (/data/resume)...")
    stdin, stdout, stderr = ssh.exec_command(f"ssh root@{K8S_HOST} 'ls -lh {K8S_WEB_DIR}'")
    print(stdout.read().decode('utf-8'))

    print("\n[*] Checking 4-replica pods in namespace 'web'...")
    stdin, stdout, stderr = ssh.exec_command(f"ssh root@{K8S_HOST} 'kubectl get pods -n web -o wide'")
    print(stdout.read().decode('utf-8'))

    ssh.close()

    # Clean local tar
    if os.path.exists(LOCAL_TAR):
        os.remove(LOCAL_TAR)

    # Test Public Live Endpoint
    print(f"\n[*] Testing public live site: {LIVE_URL}...")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            status = resp.status
            content = resp.read().decode('utf-8', errors='replace')
            print(f"[✓] HTTP Response: {status} OK")
            
            checks = [
                "ENTERPRISE CLOUD & KUBERNETES ARCHITECT",
                "HA Kubernetes Cluster & Ingress",
                "Pi-hole v6 / Unbound DNSSEC",
                "Zero-Balloon Memory Tuning",
                "NovaFlix",
                "AegisDNS"
            ]
            for chk in checks:
                if chk.lower() in content.lower():
                    print(f"    [✓] Confirmed live on cluster: {chk}")
                else:
                    print(f"    [✗] Warning - check missing: {chk}")
    except Exception as e:
        print(f"[!] Live URL verification error: {e}")

if __name__ == "__main__":
    deploy_via_pve()
