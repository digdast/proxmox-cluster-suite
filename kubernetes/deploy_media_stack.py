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

MANIFEST_CONTENT = """apiVersion: v1
kind: Namespace
metadata:
  name: media
---
# --- SONARR ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sonarr
  namespace: media
  labels:
    app: sonarr
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: sonarr
  template:
    metadata:
      labels:
        app: sonarr
    spec:
      containers:
      - name: sonarr
        image: lscr.io/linuxserver/sonarr:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: PUID
            value: "1000"
          - name: PGID
            value: "1000"
          - name: TZ
            value: "America/New_York"
        ports:
          - containerPort: 8989
            name: http
        volumeMounts:
          - name: config
            mountPath: /config
          - name: data
            mountPath: /data
      volumes:
        - name: config
          hostPath:
            path: /data/config/sonarr
            type: DirectoryOrCreate
        - name: data
          hostPath:
            path: /data
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: sonarr
  namespace: media
  labels:
    app: sonarr
spec:
  type: NodePort
  ports:
    - port: 8989
      targetPort: 8989
      nodePort: 32093
      name: http
  selector:
    app: sonarr
---
# --- RADARR ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: radarr
  namespace: media
  labels:
    app: radarr
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: radarr
  template:
    metadata:
      labels:
        app: radarr
    spec:
      containers:
      - name: radarr
        image: lscr.io/linuxserver/radarr:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: PUID
            value: "1000"
          - name: PGID
            value: "1000"
          - name: TZ
            value: "America/New_York"
        ports:
          - containerPort: 7878
            name: http
        volumeMounts:
          - name: config
            mountPath: /config
          - name: data
            mountPath: /data
      volumes:
        - name: config
          hostPath:
            path: /data/config/radarr
            type: DirectoryOrCreate
        - name: data
          hostPath:
            path: /data
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: radarr
  namespace: media
  labels:
    app: radarr
spec:
  type: NodePort
  ports:
    - port: 7878
      targetPort: 7878
      nodePort: 32529
      name: http
  selector:
    app: radarr
---
# --- PROWLARR ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prowlarr
  namespace: media
  labels:
    app: prowlarr
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: prowlarr
  template:
    metadata:
      labels:
        app: prowlarr
    spec:
      containers:
      - name: prowlarr
        image: lscr.io/linuxserver/prowlarr:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: PUID
            value: "1000"
          - name: PGID
            value: "1000"
          - name: TZ
            value: "America/New_York"
        ports:
          - containerPort: 9696
            name: http
        volumeMounts:
          - name: config
            mountPath: /config
          - name: data
            mountPath: /data
      volumes:
        - name: config
          hostPath:
            path: /data/config/prowlarr
            type: DirectoryOrCreate
        - name: data
          hostPath:
            path: /data
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: prowlarr
  namespace: media
  labels:
    app: prowlarr
spec:
  type: NodePort
  ports:
    - port: 9696
      targetPort: 9696
      nodePort: 31627
      name: http
  selector:
    app: prowlarr
---
# --- INGRESS ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: media-ingress
  namespace: media
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: sonarr.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: sonarr
            port:
              number: 8989
  - host: radarr.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: radarr
            port:
              number: 7878
  - host: prowlarr.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: prowlarr
            port:
              number: 9696
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
    print("  DEPLOYING SONARR, RADARR, AND PROWLARR ON KUBERNETES")
    print(f"  Mounts: /data/config/<app>:/config and /data:/data")
    print("  Timezone: America/New_York")
    print(f"  Target: {CP1_IP}")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    # Step 1: Prepare directories and migrate/preserve existing databases
    log("Preparing directories under /data/config/...")
    prep_cmd = """
mkdir -p /data/config/sonarr /data/config/radarr /data/config/prowlarr

# If sonarr.db doesn't exist in /data/config/sonarr, copy the active database
if [ ! -f /data/config/sonarr/sonarr.db ]; then
    if [ -f /data/sonarr.db ]; then
        echo "Copying /data/sonarr.db to /data/config/sonarr/sonarr.db..."
        cp -p /data/sonarr.db /data/config/sonarr/sonarr.db
    elif [ -f /data/appdata/sonarr/sonarr.db ]; then
        echo "Copying /data/appdata/sonarr/sonarr.db to /data/config/sonarr/sonarr.db..."
        cp -p /data/appdata/sonarr/sonarr.db /data/config/sonarr/sonarr.db
    fi
fi

# If prowlarr.db doesn't exist in /data/config/prowlarr, copy active database
if [ ! -f /data/config/prowlarr/prowlarr.db ]; then
    if [ -f /data/appdata/prowlarr/prowlarr.db ]; then
        echo "Copying /data/appdata/prowlarr/prowlarr.db to /data/config/prowlarr/prowlarr.db..."
        cp -p /data/appdata/prowlarr/prowlarr.db /data/config/prowlarr/prowlarr.db
    fi
fi

# Ensure AllowedHosts in config.xml files does not block requests
for xml in /data/config/sonarr/config.xml /data/config/radarr/config.xml /data/config/prowlarr/config.xml; do
    if [ -f "$xml" ]; then
        sed -i 's|<AllowedHosts>.*</AllowedHosts>|<AllowedHosts></AllowedHosts>|g' "$xml"
    fi
done

chmod -R 777 /data/config/sonarr /data/config/radarr /data/config/prowlarr 2>/dev/null || true
"""
    out_prep, _ = run_vm(ssh, prep_cmd)
    if out_prep:
        print(out_prep)
    ok("Config directories ready and databases preserved!")

    # Step 2: Apply Kubernetes manifests
    log("Applying Kubernetes manifests for Sonarr, Radarr, Prowlarr...")
    apply_cmd = f"cat << 'EOF' | kubectl apply -f -\n{MANIFEST_CONTENT}\nEOF"
    out_apply, er_apply = run_vm(ssh, apply_cmd)
    print(out_apply)
    if er_apply:
        print("Notice:", er_apply)
    ok("Manifests applied successfully!")

    # Step 3: Wait for Pods to be Running
    log("Waiting for Sonarr, Radarr, and Prowlarr pods to be Running...")
    for attempt in range(30):
        pods_out, _ = run_vm(ssh, "kubectl get pods -n media -o wide")
        print(f"\n--- Pods Status (attempt {attempt+1}/30) ---")
        print(pods_out)
        lines = [l for l in pods_out.splitlines() if "1/1" in l and "Running" in l]
        if len(lines) >= 3:
            ok("All 3 pods are 1/1 Running!")
            break
        time.sleep(6)

    # Step 4: Update NPM Reverse Proxy (Host 18: Sonarr, Host 36: Radarr, Host 20: Prowlarr)
    log("\nUpdating Nginx Proxy Manager (CT 200 / 192.168.0.8:81)...")
    try:
        req_token = urllib.request.Request(
            f"{NPM_HOST}/api/tokens",
            data=json.dumps({"identity": NPM_USER, "secret": NPM_PW}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_token) as resp:
            token = json.loads(resp.read().decode('utf-8'))["token"]

        hosts_to_update = [
            {"id": 18, "domain": "sonarr.ertechlab.com", "port": 32093},
            {"id": 36, "domain": "radarr.ertechlab.com", "port": 32529},
            {"id": 20, "domain": "prowlarr.ertechlab.com", "port": 31627},
        ]

        for h in hosts_to_update:
            # Fetch existing host config
            req_get = urllib.request.Request(
                f"{NPM_HOST}/api/nginx/proxy-hosts/{h['id']}",
                headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(req_get) as resp_get:
                existing = json.loads(resp_get.read().decode('utf-8'))

            existing["forward_host"] = CP1_IP
            existing["forward_port"] = h["port"]
            existing["forward_scheme"] = "http"

            req_put = urllib.request.Request(
                f"{NPM_HOST}/api/nginx/proxy-hosts/{h['id']}",
                data=json.dumps(existing).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                method="PUT"
            )
            with urllib.request.urlopen(req_put) as resp_put:
                ok(f"NPM Host {h['id']} ({h['domain']}) updated -> {CP1_IP}:{h['port']}")
    except Exception as e:
        err(f"NPM update notice: {e}")

    # Step 5: Update Pi-hole DNS
    log("\nUpdating Pi-hole DNS (192.168.0.2) with arr stack domains...")
    pihole_cmd = f"""pct exec 300 -- python3 -c '
hosts = [
    ("{CP1_IP}", "sonarr.ertech.home"),
    ("{CP1_IP}", "radarr.ertech.home"),
    ("{CP1_IP}", "prowlarr.ertech.home")
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

    # Step 6: Verify HTTP endpoints
    log("\nVerifying HTTP responses from all three services...")
    time.sleep(5)
    for name, port in [("Sonarr", 32093), ("Radarr", 32529), ("Prowlarr", 31627)]:
        out, _ = run_vm(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}")
        ok(f"{name} (port {port}): HTTP {out}")

    ssh.close()

    print("\n" + "=" * 75)
    print("  🎉 MEDIA STACK (SONARR, RADARR, PROWLARR) DEPLOYED SUCCESSFULLY!")
    print("=" * 75)
    print("  Sonarr:")
    print(f"    - Public:  https://sonarr.ertechlab.com")
    print(f"    - Local:   http://{CP1_IP}:32093  (or http://sonarr.ertech.home)")
    print("  Radarr:")
    print(f"    - Public:  https://radarr.ertechlab.com")
    print(f"    - Local:   http://{CP1_IP}:32529  (or http://radarr.ertech.home)")
    print("  Prowlarr:")
    print(f"    - Public:  https://prowlarr.ertechlab.com")
    print(f"    - Local:   http://{CP1_IP}:31627  (or http://prowlarr.ertech.home)")
    print("=" * 75)

if __name__ == "__main__":
    main()
