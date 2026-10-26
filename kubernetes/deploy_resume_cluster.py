import os
import sys
import paramiko
import urllib.request
import ssl

sys.stdout.reconfigure(encoding='utf-8')

LOCAL_SITE_DIR = r"C:\scripts\resume_ertechlab_deploy\site"
REMOTE_K8S_HOST = "192.168.0.81"
REMOTE_USER = "root"
REMOTE_PW = "sone_420"
REMOTE_WEB_DIR = "/data/resume"
LIVE_URL = "https://resume.ertechlab.com"

def deploy():
    print("=" * 70)
    print(f"  DEPLOYING UPDATED RESUME TO K8S CLUSTER ({LIVE_URL})")
    print("=" * 70)

    print(f"[*] Connecting to {REMOTE_K8S_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(REMOTE_K8S_HOST, username=REMOTE_USER, password=REMOTE_PW, timeout=10)
    print("[✓] SSH connection established.")

    sftp = ssh.open_sftp()
    
    # Ensure remote directory exists
    ssh.exec_command(f"mkdir -p {REMOTE_WEB_DIR}")

    # Upload all site files
    print(f"\n[*] Uploading site files from {LOCAL_SITE_DIR} to {REMOTE_WEB_DIR}...")
    for filename in os.listdir(LOCAL_SITE_DIR):
        local_path = os.path.join(LOCAL_SITE_DIR, filename)
        if os.path.isfile(local_path):
            remote_path = f"{REMOTE_WEB_DIR}/{filename}"
            size = os.path.getsize(local_path)
            sftp.put(local_path, remote_path)
            print(f"    - Uploaded {filename} ({size:,} bytes) -> {remote_path}")

    sftp.close()

    # Set permissions
    print("\n[*] Setting permissions on shared storage...")
    ssh.exec_command(f"chmod -R 755 {REMOTE_WEB_DIR}")

    # Verify pods in web namespace
    stdin, stdout, stderr = ssh.exec_command("kubectl get pods -n web -o wide")
    print(f"\n[*] Active 4-replica pods:\n{stdout.read().decode('utf-8')}")

    ssh.close()

    # Test live endpoint
    print(f"\n[*] Testing public live site: {LIVE_URL}...")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            print(f"[✓] HTTP Response: {resp.status} OK")
    except Exception as e:
        print(f"[!] Live URL test: {e}")

    print("\n" + "=" * 70)
    print("  RESUME CLUSTER DEPLOYMENT COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    deploy()
