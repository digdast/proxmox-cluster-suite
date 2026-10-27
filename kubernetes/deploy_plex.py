import os
import sys
import time
import json
import urllib.request
import paramiko
import base64

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
SSH_KEY_PATH = "/root/.ssh/id_rsa"
CP1_IP = "192.168.0.81"

NPM_HOST = "http://192.168.0.8:81"
NPM_USER = "efrain.acetech@gmail.com"
NPM_PW = "Chloe_12152009"

PLEX_MANIFEST = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: plex
  namespace: media
  labels:
    app: plex
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: plex
  template:
    metadata:
      labels:
        app: plex
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: plex
        image: lscr.io/linuxserver/plex:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: PUID
            value: "1000"
          - name: PGID
            value: "1000"
          - name: TZ
            value: "America/New_York"
          - name: VERSION
            value: "docker"
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            memory: 5Gi
        volumeMounts:
          - name: config
            mountPath: /config
          - name: data
            mountPath: /data
          - name: transcode
            mountPath: /transcode
          - name: dshm
            mountPath: /dev/shm
      volumes:
        - name: config
          hostPath:
            path: /var/lib/plex/config
            type: DirectoryOrCreate
        - name: data
          hostPath:
            path: /data
            type: Directory
        - name: transcode
          emptyDir:
            medium: Memory
            sizeLimit: 2Gi
        - name: dshm
          emptyDir:
            medium: Memory
            sizeLimit: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: plex
  namespace: media
  labels:
    app: plex
spec:
  type: ClusterIP
  ports:
    - port: 32400
      targetPort: 32400
      name: plex-web
      protocol: TCP
  selector:
    app: plex
"""

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def run_vm(ssh_pve, cmd):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -o BatchMode=yes -i {SSH_KEY_PATH} root@{CP1_IP} '{escaped}'"
    stdin, stdout, stderr = ssh_pve.exec_command(exec_str)
    return stdout.read().decode('utf-8', errors='replace').strip(), stderr.read().decode('utf-8', errors='replace').strip()

def main():
    print("=" * 70)
    print("  🚀 DEPLOYING OPTIMIZED PLEX MEDIA SERVER ON K3S")
    print("=" * 70)

    log(f"Connecting to Proxmox VE Host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to {PVE_HOST}")

    # Step 1: Kernel Tuning
    log("Applying Linux Kernel optimization parameters...")
    sysctl_content = """
fs.inotify.max_user_watches = 1048576
fs.inotify.max_user_instances = 1024
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
"""
    b64_sysctl = base64.b64encode(sysctl_content.encode()).decode()
    run_vm(ssh, f"echo {b64_sysctl} | base64 -d > /etc/sysctl.d/99-plex.conf && sysctl -p /etc/sysctl.d/99-plex.conf")
    ok("Kernel parameters applied successfully.")

    # Step 2: Apply Manifest
    log("Applying Kubernetes Deployment manifest...")
    b64_manifest = base64.b64encode(PLEX_MANIFEST.encode()).decode()
    out_apply, _ = run_vm(ssh, f"echo {b64_manifest} | base64 -d | kubectl apply -f -")
    print(" ", out_apply)

    # Step 3: Wait for Pod
    log("Waiting for Plex pod to become Running...")
    for attempt in range(25):
        pods_out, _ = run_vm(ssh, "kubectl get pods -n media -l app=plex -o wide")
        status_line = pods_out.splitlines()[-1] if pods_out else ""
        print(f"  [{attempt+1}/25] {status_line}")
        if "1/1" in status_line and "Running" in status_line:
            ok("Plex pod is 1/1 Running on host network!")
            break
        time.sleep(4)

    # Step 4: Update NPM Reverse Proxy
    log("Updating Nginx Proxy Manager (Host 21: plexserver.ertechlab.com)...")
    try:
        req_token = urllib.request.Request(
            f"{NPM_HOST}/api/tokens",
            data=json.dumps({"identity": NPM_USER, "secret": NPM_PW}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_token) as resp:
            token = json.loads(resp.read().decode('utf-8'))["token"]

        req_g = urllib.request.Request(f"{NPM_HOST}/api/nginx/proxy-hosts/21", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req_g) as rg:
            hdata = json.loads(rg.read().decode('utf-8'))

        pl = {
            "domain_names": hdata["domain_names"],
            "forward_scheme": "http",
            "forward_host": CP1_IP,
            "forward_port": 32400,
            "access_list_id": hdata.get("access_list_id", 0),
            "certificate_id": hdata.get("certificate_id", 0),
            "ssl_forced": hdata.get("ssl_forced", False),
            "caching_enabled": False,
            "block_exploits": hdata.get("block_exploits", True),
            "advanced_config": hdata.get("advanced_config", ""),
            "allow_websocket_upgrade": True,
            "http2_support": True,
            "hsts_enabled": False,
            "hsts_subdomains": False,
            "locations": []
        }
        req_p = urllib.request.Request(
            f"{NPM_HOST}/api/nginx/proxy-hosts/21",
            data=json.dumps(pl).encode('utf-8'),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="PUT"
        )
        with urllib.request.urlopen(req_p) as rp:
            ok(f"NPM Host 21 (plexserver.ertechlab.com) updated -> {CP1_IP}:32400")
    except Exception as e:
        err(f"NPM update notice: {e}")

    ssh.close()
    ok("Plex Media Server deployment and configuration completed!")

if __name__ == "__main__":
    main()
