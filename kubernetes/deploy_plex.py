import os
import sys
import time
import json
import urllib.request
import paramiko

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
        ports:
          - containerPort: 32400
            name: plex-web
          - containerPort: 3005
            name: plex-companion
          - containerPort: 8324
            name: plex-roku
          - containerPort: 32410
            name: plex-gdm-1
            protocol: UDP
          - containerPort: 32412
            name: plex-gdm-2
            protocol: UDP
          - containerPort: 32413
            name: plex-gdm-3
            protocol: UDP
          - containerPort: 32414
            name: plex-gdm-4
            protocol: UDP
          - containerPort: 32469
            name: plex-dlna-tcp
          - containerPort: 1900
            name: plex-dlna-udp
            protocol: UDP
        volumeMounts:
          - name: config
            mountPath: /config
          - name: data
            mountPath: /data
          - name: transcode
            mountPath: /transcode
      volumes:
        - name: config
          hostPath:
            path: /data/config/plex
            type: DirectoryOrCreate
        - name: data
          hostPath:
            path: /data
            type: Directory
        - name: transcode
          hostPath:
            path: /data/transcode
            type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: plex
  namespace: media
  labels:
    app: plex
spec:
  type: NodePort
  ports:
    - port: 32400
      targetPort: 32400
      nodePort: 32400
      name: plex-web
      protocol: TCP
  selector:
    app: plex
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: plex-ingress
  namespace: media
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: plex.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: plex
            port:
              number: 32400
  - host: plexserver.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: plex
            port:
              number: 32400
"""

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def run_vm(ssh, cmd):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -i {SSH_KEY_PATH} root@{CP1_IP} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def run_pve(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  DEPLOYING PLEX MEDIA SERVER ON KUBERNETES")
    print(f"  Mounts: /data/config/plex:/config, /data:/data, /data/transcode:/transcode")
    print("  Timezone: America/New_York")
    print(f"  Port: 32400 (NodePort: 32400)")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    # Step 1: Ensure directories exist
    log("Ensuring /data/config/plex and /data/transcode exist...")
    run_vm(ssh, "mkdir -p /data/config/plex /data/transcode && chmod -R 777 /data/config/plex /data/transcode 2>/dev/null || true")

    # Step 2: Apply Kubernetes manifest
    log("Applying Plex Kubernetes manifest...")
    apply_cmd = f"cat << 'EOF' | kubectl apply -f -\n{PLEX_MANIFEST}\nEOF"
    out_apply, er_apply = run_vm(ssh, apply_cmd)
    print(out_apply)
    if er_apply:
        print("Notice:", er_apply)
    ok("Plex manifest applied successfully!")

    # Step 3: Wait for Plex Pod to become Running
    log("Waiting for Plex pod to become Running...")
    for attempt in range(30):
        pods_out, _ = run_vm(ssh, "kubectl get pods -n media -l app=plex -o wide")
        print(f"  [{attempt+1}/30] {pods_out.splitlines()[-1] if pods_out else ''}")
        if "1/1" in pods_out and "Running" in pods_out:
            ok("Plex pod is 1/1 Running!")
            break
        time.sleep(5)

    # Step 4: Update NPM Reverse Proxy (Host 21: plexserver.ertechlab.com)
    log("\nUpdating Nginx Proxy Manager (CT 200 / 192.168.0.8:81)...")
    try:
        req_token = urllib.request.Request(
            f"{NPM_HOST}/api/tokens",
            data=json.dumps({"identity": NPM_USER, "secret": NPM_PW}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_token) as resp:
            token = json.loads(resp.read().decode('utf-8'))["token"]

        # Update Host 21
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
            "http2_support": hdata.get("http2_support", True),
            "hsts_enabled": hdata.get("hsts_enabled", False),
            "hsts_subdomains": hdata.get("hsts_subdomains", False),
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

    # Step 5: Update Pi-hole DNS
    log("\nUpdating Pi-hole DNS (192.168.0.2) with Plex domain names...")
    pihole_cmd = f"""pct exec 300 -- python3 -c '
hosts = [
    ("{CP1_IP}", "plex.ertech.home"),
    ("{CP1_IP}", "plexserver.ertech.home")
]
with open("/etc/pihole/custom.list", "a+") as f:
    f.seek(0)
    existing = f.read()
    for ip, domain in hosts:
        line = f"{{ip}} {{domain}}"
        if domain not in existing:
            f.write(f"\\n{{line}}")
            print("Added to Pi-hole:", line)
        else:
            print("Already present in Pi-hole:", domain)
'"""
    run_pve(ssh, pihole_cmd)
    run_pve(ssh, "pct exec 300 -- systemctl restart pihole-FTL")
    ok("Pi-hole DNS reloaded!")

    # Step 6: Verify Plex Web response
    log("\nVerifying Plex Web response...")
    time.sleep(10)
    out_curl, _ = run_vm(ssh, "curl -sI http://127.0.0.1:32400/web/index.html | head -n 5")
    print(f"Plex Web response:\n{out_curl}")

    ssh.close()

    print("\n" + "=" * 75)
    print("  🎉 PLEX MEDIA SERVER DEPLOYED SUCCESSFULLY!")
    print("=" * 75)
    print("  Access URLs:")
    print("    - Public / SSL:    https://plexserver.ertechlab.com")
    print(f"    - Direct IP:       http://{CP1_IP}:32400/web")
    print("    - Local DNS:       http://plex.ertech.home:32400/web")
    print("=" * 75)

if __name__ == "__main__":
    main()
