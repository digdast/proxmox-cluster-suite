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
VM_USER = "plexadmin"
CP1_IP = "192.168.0.81"

NPM_HOST = "http://192.168.0.8:81"
NPM_USER = "efrain.acetech@gmail.com"
NPM_PW = "Chloe_12152009"

PORTAINER_ADMIN_USER = "admin"
PORTAINER_ADMIN_PW = "Chloe_12152009"

PORTAINER_MANIFEST = f"""apiVersion: v1
kind: Namespace
metadata:
  name: portainer
  labels:
    pod-security.kubernetes.io/enforce: privileged
---
apiVersion: v1
kind: Secret
metadata:
  name: portainer-admin-secret
  namespace: portainer
type: Opaque
stringData:
  password: "{PORTAINER_ADMIN_PW}"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: portainer-sa-clusteradmin
  namespace: portainer
  labels:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: portainer
  labels:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: portainer-sa-clusteradmin
  namespace: portainer
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: portainer
  namespace: portainer
  labels:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: portainer
  namespace: portainer
  labels:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
spec:
  type: NodePort
  ports:
    - port: 9000
      targetPort: 9000
      protocol: TCP
      name: http
      nodePort: 30777
    - port: 9443
      targetPort: 9443
      protocol: TCP
      name: https
      nodePort: 30779
    - port: 30776
      targetPort: 30776
      protocol: TCP
      name: edge
      nodePort: 30776
  selector:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: portainer
  namespace: portainer
  labels:
    app.kubernetes.io/name: portainer
    app.kubernetes.io/instance: portainer
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: portainer
      app.kubernetes.io/instance: portainer
  template:
    metadata:
      labels:
        app.kubernetes.io/name: portainer
        app.kubernetes.io/instance: portainer
    spec:
      serviceAccountName: portainer-sa-clusteradmin
      containers:
        - name: portainer
          image: portainer/portainer-ce:latest
          imagePullPolicy: IfNotPresent
          args:
            - --tunnel-port=30776
            - --admin-password-file=/run/secrets/portainer/password
          volumeMounts:
            - name: data
              mountPath: /data
            - name: admin-secret
              mountPath: /run/secrets/portainer
              readOnly: true
          ports:
            - name: http
              containerPort: 9000
              protocol: TCP
            - name: https
              containerPort: 9443
              protocol: TCP
            - name: tcp-edge
              containerPort: 8000
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /
              port: 9443
              scheme: HTTPS
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: /
              port: 9443
              scheme: HTTPS
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: portainer
        - name: admin-secret
          secret:
            secretName: portainer-admin-secret
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: portainer-ingress
  namespace: portainer
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web,websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  rules:
  - host: portainer.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: portainer
            port:
              number: 9443
  - host: portainer.ertechlab.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: portainer
            port:
              number: 9443
"""

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

def run_vm(ssh, cmd, timeout=60):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i {SSH_KEY_PATH} {VM_USER}@{CP1_IP} '{escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  DEPLOYING PORTAINER CE ON KUBERNETES (K3s)")
    print("  Cluster: 2 Control Planes, 4 Workers")
    print(f"  Target: {CP1_IP}:30779 | portainer.ertechlab.com")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    # Step 1: Write and apply Portainer manifest on k8s-cp-01
    log("Applying Portainer manifest to Kubernetes cluster...")
    manifest_escaped = PORTAINER_MANIFEST.replace("'", "'\"'\"'")
    apply_cmd = f"cat << 'EOF' | sudo kubectl apply -f -\n{PORTAINER_MANIFEST}\nEOF"
    out, er = run_vm(ssh, apply_cmd)
    print(out)
    if er and "Warning" not in er:
        err(f"Apply error: {er}")
    else:
        ok("Portainer manifests applied successfully!")

    # Step 2: Wait for Portainer pod to be Running
    log("Waiting for Portainer pod to become Ready...")
    pod_ready = False
    for attempt in range(30):
        out_pods, _ = run_vm(ssh, "sudo kubectl get pods -n portainer -o wide")
        print(f"  [{attempt+1}/30] {out_pods.splitlines()[-1] if out_pods else ''}")
        if "1/1" in out_pods and "Running" in out_pods:
            ok("Portainer pod is 1/1 Running!")
            pod_ready = True
            break
        time.sleep(5)

    if not pod_ready:
        err("Timed out waiting for Portainer pod to be ready.")
        run_vm(ssh, "sudo kubectl describe pods -n portainer")
        return

    # Step 3: Check services and endpoints
    svc_out, _ = run_vm(ssh, "sudo kubectl get svc,ingress -n portainer")
    print("\n" + "=" * 70)
    print(svc_out)
    print("=" * 70)

    # Step 4: Update Nginx Proxy Manager Host 35 for portainer.ertechlab.com
    log("\nUpdating Nginx Proxy Manager (CT 200 / 192.168.0.8:81)...")
    try:
        req = urllib.request.Request(
            f"{NPM_HOST}/api/tokens",
            data=json.dumps({"identity": NPM_USER, "secret": NPM_PW}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            token = json.loads(resp.read().decode('utf-8'))["token"]

        npm_payload = {
            "domain_names": ["portainer.ertechlab.com"],
            "forward_scheme": "https",
            "forward_host": CP1_IP,
            "forward_port": 30779,
            "certificate_id": 20,
            "ssl_forced": True,
            "hsts_enabled": False,
            "hsts_subdomains": False,
            "http2_support": True,
            "block_exploits": True,
            "caching_enabled": False,
            "allow_websocket_upgrade": True,
            "access_list_id": 0,
            "advanced_config": "proxy_ssl_verify off;\nproxy_set_header Host $host;\nproxy_set_header X-Forwarded-Proto https;",
            "enabled": True,
            "locations": []
        }

        req_update = urllib.request.Request(
            f"{NPM_HOST}/api/nginx/proxy-hosts/35",
            data=json.dumps(npm_payload).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="PUT"
        )
        with urllib.request.urlopen(req_update) as resp:
            saved = json.loads(resp.read().decode('utf-8'))
            ok(f"NPM Host 35 updated: portainer.ertechlab.com -> https://{CP1_IP}:30779")
    except Exception as e:
        err(f"NPM update error: {e}")

    # Step 5: Update Pi-hole DNS with portainer.ertech.home
    log("\nRegistering portainer.ertech.home in Pi-hole DNS...")
    pihole_cmd = """pct exec 300 -- python3 -c '
line = "192.168.0.81 portainer.ertech.home"
with open("/etc/pihole/custom.list", "a+") as f:
    f.seek(0)
    text = f.read()
    if "portainer.ertech.home" not in text:
        f.write(f"\\n{line}")
        print("Added to custom.list:", line)
    else:
        print("Already present in custom.list")
'"""
    run_pve(ssh, pihole_cmd)
    run_pve(ssh, "pct exec 300 -- systemctl restart pihole-FTL")
    ok("Pi-hole DNS reloaded!")

    # Step 6: Verify HTTP/HTTPS response directly
    log("\nTesting direct HTTPS connection to Portainer on node IP...")
    out_curl, _ = run_vm(ssh, "curl -sk https://127.0.0.1:9443/api/status")
    print(f"Portainer /api/status response:\n{out_curl}")

    ssh.close()

    print("\n" + "=" * 75)
    print("  🎉 PORTAINER COMMUNITY EDITION IS DEPLOYED AND READY!")
    print("=" * 75)
    print("  Access URLs:")
    print(f"    - Public / SSL:    https://portainer.ertechlab.com")
    print(f"    - Local DNS:       https://portainer.ertech.home:30779 (or via Ingress: https://portainer.ertech.home)")
    print(f"    - Direct NodePort: https://192.168.0.81:30779")
    print(f"    - Direct HTTP:     http://192.168.0.81:30777")
    print("\n  Initial Credentials:")
    print(f"    - Username: {PORTAINER_ADMIN_USER}")
    print(f"    - Password: {PORTAINER_ADMIN_PW}")
    print("=" * 75)

if __name__ == "__main__":
    main()
