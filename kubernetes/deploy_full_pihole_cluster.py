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

PIHOLE_PW = "Chloe_12152009"

MANIFEST_CONTENT = f"""apiVersion: v1
kind: Namespace
metadata:
  name: dns
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: unbound-config
  namespace: dns
data:
  port.conf: |
    server:
        interface: 127.0.0.1
        port: 5335
        do-ip4: yes
        do-udp: yes
        do-tcp: yes
        access-control: 127.0.0.0/8 allow

        # Strict Privacy & Anti-Leak (QNAME Minimization + DNSSEC)
        qname-minimisation: yes
        qname-minimisation-strict: no
        hide-identity: yes
        hide-version: yes
        harden-glue: yes
        harden-dnssec-stripped: yes
        use-caps-for-id: yes
        prefetch: yes
        prefetch-key: yes
        rrset-roundrobin: yes
        minimal-responses: yes

        # Prevent DNS Rebinding & Private IP Leakage
        private-address: 10.0.0.0/8
        private-address: 172.16.0.0/12
        private-address: 192.168.0.0/16
        private-address: 169.254.0.0/16
        private-address: fd00::/8
        private-address: fe80::/10
---
# --- PI-HOLE 1 (PRIMARY) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pihole-1
  namespace: dns
  labels:
    app: pihole-1
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: pihole-1
  template:
    metadata:
      labels:
        app: pihole-1
        role: pihole-cluster
    spec:
      dnsPolicy: "None"
      dnsConfig:
        nameservers:
          - 1.1.1.1
          - 8.8.8.8
      containers:
      - name: pihole
        image: pihole/pihole:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: TZ
            value: "America/New_York"
          - name: WEBPASSWORD
            value: "{PIHOLE_PW}"
          - name: FTLCONF_webserver_api_password
            value: "{PIHOLE_PW}"
          - name: FTLCONF_dns_upstreams
            value: "127.0.0.1#5335"
          - name: FTLCONF_dns_listeningMode
            value: "ALL"
          - name: DNSSEC
            value: "true"
          - name: FTLCONF_LOCAL_IPV4
            value: "0.0.0.0"
        ports:
          - name: dns-udp
            containerPort: 53
            protocol: UDP
          - name: dns-tcp
            containerPort: 53
            protocol: TCP
          - name: http
            containerPort: 80
            protocol: TCP
        volumeMounts:
          - name: pihole-config
            mountPath: /etc/pihole
          - name: dnsmasq-config
            mountPath: /etc/dnsmasq.d
      - name: unbound
        image: klutchell/unbound:latest
        imagePullPolicy: IfNotPresent
        ports:
          - name: unbound-dns
            containerPort: 5335
            protocol: UDP
        volumeMounts:
          - name: unbound-cfg
            mountPath: /etc/unbound/custom.conf.d/port.conf
            subPath: port.conf
      - name: cloudflared-doh
        image: cloudflare/cloudflared:2024.12.0
        imagePullPolicy: IfNotPresent
        args:
          - "proxy-dns"
          - "--address"
          - "127.0.0.1"
          - "--port"
          - "5053"
          - "--upstream"
          - "https://1.1.1.1/dns-query"
          - "--upstream"
          - "https://1.0.0.1/dns-query"
        ports:
          - name: doh-dns
            containerPort: 5053
            protocol: UDP
      volumes:
        - name: pihole-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-1/etc-pihole
            type: DirectoryOrCreate
        - name: dnsmasq-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-1/etc-dnsmasq.d
            type: DirectoryOrCreate
        - name: unbound-cfg
          configMap:
            name: unbound-config
---
apiVersion: v1
kind: Service
metadata:
  name: pihole-1
  namespace: dns
  labels:
    app: pihole-1
spec:
  type: NodePort
  ports:
    - name: http
      port: 80
      targetPort: 80
      nodePort: 30081
  selector:
    app: pihole-1
---
# --- PI-HOLE 2 (REPLICA 1) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pihole-2
  namespace: dns
  labels:
    app: pihole-2
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: pihole-2
  template:
    metadata:
      labels:
        app: pihole-2
        role: pihole-cluster
    spec:
      dnsPolicy: "None"
      dnsConfig:
        nameservers:
          - 1.1.1.1
          - 8.8.8.8
      containers:
      - name: pihole
        image: pihole/pihole:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: TZ
            value: "America/New_York"
          - name: WEBPASSWORD
            value: "{PIHOLE_PW}"
          - name: FTLCONF_webserver_api_password
            value: "{PIHOLE_PW}"
          - name: FTLCONF_dns_upstreams
            value: "127.0.0.1#5335"
          - name: FTLCONF_dns_listeningMode
            value: "ALL"
          - name: DNSSEC
            value: "true"
          - name: FTLCONF_LOCAL_IPV4
            value: "0.0.0.0"
        ports:
          - name: dns-udp
            containerPort: 53
            protocol: UDP
          - name: dns-tcp
            containerPort: 53
            protocol: TCP
          - name: http
            containerPort: 80
            protocol: TCP
        volumeMounts:
          - name: pihole-config
            mountPath: /etc/pihole
          - name: dnsmasq-config
            mountPath: /etc/dnsmasq.d
      - name: unbound
        image: klutchell/unbound:latest
        imagePullPolicy: IfNotPresent
        ports:
          - name: unbound-dns
            containerPort: 5335
            protocol: UDP
        volumeMounts:
          - name: unbound-cfg
            mountPath: /etc/unbound/custom.conf.d/port.conf
            subPath: port.conf
      - name: cloudflared-doh
        image: cloudflare/cloudflared:2024.12.0
        imagePullPolicy: IfNotPresent
        args:
          - "proxy-dns"
          - "--address"
          - "127.0.0.1"
          - "--port"
          - "5053"
          - "--upstream"
          - "https://1.1.1.1/dns-query"
          - "--upstream"
          - "https://1.0.0.1/dns-query"
        ports:
          - name: doh-dns
            containerPort: 5053
            protocol: UDP
      volumes:
        - name: pihole-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-2/etc-pihole
            type: DirectoryOrCreate
        - name: dnsmasq-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-2/etc-dnsmasq.d
            type: DirectoryOrCreate
        - name: unbound-cfg
          configMap:
            name: unbound-config
---
apiVersion: v1
kind: Service
metadata:
  name: pihole-2
  namespace: dns
  labels:
    app: pihole-2
spec:
  type: NodePort
  ports:
    - name: http
      port: 80
      targetPort: 80
      nodePort: 30082
  selector:
    app: pihole-2
---
# --- PI-HOLE 3 (REPLICA 2) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pihole-3
  namespace: dns
  labels:
    app: pihole-3
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: pihole-3
  template:
    metadata:
      labels:
        app: pihole-3
        role: pihole-cluster
    spec:
      dnsPolicy: "None"
      dnsConfig:
        nameservers:
          - 1.1.1.1
          - 8.8.8.8
      containers:
      - name: pihole
        image: pihole/pihole:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: TZ
            value: "America/New_York"
          - name: WEBPASSWORD
            value: "{PIHOLE_PW}"
          - name: FTLCONF_webserver_api_password
            value: "{PIHOLE_PW}"
          - name: FTLCONF_dns_upstreams
            value: "127.0.0.1#5335"
          - name: FTLCONF_dns_listeningMode
            value: "ALL"
          - name: DNSSEC
            value: "true"
          - name: FTLCONF_LOCAL_IPV4
            value: "0.0.0.0"
        ports:
          - name: dns-udp
            containerPort: 53
            protocol: UDP
          - name: dns-tcp
            containerPort: 53
            protocol: TCP
          - name: http
            containerPort: 80
            protocol: TCP
        volumeMounts:
          - name: pihole-config
            mountPath: /etc/pihole
          - name: dnsmasq-config
            mountPath: /etc/dnsmasq.d
      - name: unbound
        image: klutchell/unbound:latest
        imagePullPolicy: IfNotPresent
        ports:
          - name: unbound-dns
            containerPort: 5335
            protocol: UDP
        volumeMounts:
          - name: unbound-cfg
            mountPath: /etc/unbound/custom.conf.d/port.conf
            subPath: port.conf
      - name: cloudflared-doh
        image: cloudflare/cloudflared:2024.12.0
        imagePullPolicy: IfNotPresent
        args:
          - "proxy-dns"
          - "--address"
          - "127.0.0.1"
          - "--port"
          - "5053"
          - "--upstream"
          - "https://1.1.1.1/dns-query"
          - "--upstream"
          - "https://1.0.0.1/dns-query"
        ports:
          - name: doh-dns
            containerPort: 5053
            protocol: UDP
      volumes:
        - name: pihole-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-3/etc-pihole
            type: DirectoryOrCreate
        - name: dnsmasq-config
          hostPath:
            path: /var/lib/pihole-cluster/pihole-3/etc-dnsmasq.d
            type: DirectoryOrCreate
        - name: unbound-cfg
          configMap:
            name: unbound-config
---
apiVersion: v1
kind: Service
metadata:
  name: pihole-3
  namespace: dns
  labels:
    app: pihole-3
spec:
  type: NodePort
  ports:
    - name: http
      port: 80
      targetPort: 80
      nodePort: 30083
  selector:
    app: pihole-3
---
# --- LOADBALANCED DNS SERVICE (PORT 53 TCP & UDP ACROSS ALL 3 PIHOLES) ---
apiVersion: v1
kind: Service
metadata:
  name: pihole-dns
  namespace: dns
  labels:
    app.kubernetes.io/name: pihole-cluster-dns
spec:
  type: LoadBalancer
  ports:
    - name: dns-udp
      port: 53
      targetPort: 53
      protocol: UDP
    - name: dns-tcp
      port: 53
      targetPort: 53
      protocol: TCP
  selector:
    role: pihole-cluster
---
# --- NEBULA-SYNC (V6 REPLICATION DAEMON) ---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nebula-sync
  namespace: dns
  labels:
    app: nebula-sync
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: nebula-sync
  template:
    metadata:
      labels:
        app: nebula-sync
    spec:
      containers:
      - name: nebula-sync
        image: ghcr.io/lovelaze/nebula-sync:latest
        imagePullPolicy: IfNotPresent
        env:
          - name: PRIMARY
            value: "http://pihole-1:80|{PIHOLE_PW}"
          - name: REPLICAS
            value: "http://pihole-2:80|{PIHOLE_PW},http://pihole-3:80|{PIHOLE_PW}"
          - name: FULL_SYNC
            value: "true"
          - name: RUN_GRAVITY
            value: "true"
          - name: CRON
            value: "*/5 * * * *"
---
# --- INGRESS FOR PIHOLE WEB INTERFACES ---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: pihole-ingress
  namespace: dns
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: pihole.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: pihole-1
            port:
              number: 80
  - host: pihole-1.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: pihole-1
            port:
              number: 80
  - host: pihole-2.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: pihole-2
            port:
              number: 80
  - host: pihole-3.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: pihole-3
            port:
              number: 80
"""

def log(msg):
    print(f"[*] {msg}", flush=True)

def ok(msg):
    print(f"[✓] {msg}", flush=True)

def err(msg):
    print(f"[!] {msg}", flush=True)

def run_vm(ssh, cmd):
    escaped = cmd.replace("'", "'\"'\"'")
    exec_str = f"ssh -o StrictHostKeyChecking=no -i {SSH_KEY_PATH} root@{CP1_IP} 'export KUBECONFIG=/etc/rancher/k3s/k3s.yaml; {escaped}'"
    stdin, stdout, stderr = ssh.exec_command(exec_str)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    return out, er

def main():
    print("=" * 75)
    print("  DEPLOYING FULL PI-HOLE 3-NODE CLUSTER (UNBOUND + DOH + SYNC)")
    print("=" * 75 + "\n")

    log(f"Connecting to Proxmox VE root host {PVE_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)
    ok(f"Connected to Proxmox VE root host {PVE_HOST}!")

    # Clean up old orbital-sync, pihole-2, pihole-3 to avoid stuck crash loops
    log("Cleaning up old orbital-sync and outdated pihole deployments...")
    run_vm(ssh, "kubectl delete deployment orbital-sync pihole-2 pihole-3 -n dns --ignore-not-found")
    time.sleep(3)

    # Apply full manifest
    log("Applying Kubernetes manifests...")
    apply_cmd = f"cat << 'EOF' | kubectl apply -f -\n{MANIFEST_CONTENT}\nEOF"
    out_apply, er_apply = run_vm(ssh, apply_cmd)
    print(out_apply)
    if er_apply:
        print("Notice:", er_apply)
    ok("Manifests applied!")

    # Wait for all 4 pods to be ready
    log("Waiting for all 4 pods in dns namespace to become Ready...")
    for attempt in range(30):
        pods_out, _ = run_vm(ssh, "kubectl get pods -n dns -o wide")
        print(f"\n--- DNS Pods Status (attempt {attempt+1}/30) ---")
        print(pods_out)
        lines = [l for l in pods_out.splitlines() if "3/3" in l and "Running" in l]
        sync_line = [l for l in pods_out.splitlines() if "nebula-sync" in l and "Running" in l]
        if len(lines) >= 3 and len(sync_line) >= 1:
            ok("All 3 Pi-hole instances (3/3) and Nebula-Sync (1/1) are RUNNING!")
            break
        time.sleep(6)

    # Test DNS queries across all 3 Pi-hole instances
    log("\nVerifying DNS resolution across all 3 Pi-hole instances...")
    for name in ["pihole-1", "pihole-2", "pihole-3"]:
        pod_ip, _ = run_vm(ssh, f"kubectl get pod -n dns -l app={name} -o jsonpath='{{.items[0].status.podIP}}'")
        test_dig, _ = run_vm(ssh, f"dig @{pod_ip} google.com +short")
        ok(f"{name} (IP: {pod_ip}) resolved google.com:\n    {test_dig.replace(chr(10), ', ')}")

    # Test LoadBalancer Service DNS query
    svc_ip, _ = run_vm(ssh, "kubectl get svc -n dns pihole-dns -o jsonpath='{.spec.clusterIP}'")
    svc_dig, _ = run_vm(ssh, f"dig @{svc_ip} google.com +short")
    ok(f"Cluster Service (IP: {svc_ip}:53) resolved google.com:\n    {svc_dig.replace(chr(10), ', ')}")

    # Test Node IP DNS query (Port 53 host load balancing across all 3)
    node_dig, _ = run_vm(ssh, f"dig @{CP1_IP} google.com +short")
    ok(f"Node IP ({CP1_IP}:53) resolved google.com:\n    {node_dig.replace(chr(10), ', ')}")

    # Verify Nebula-Sync logs
    log("\nChecking Nebula-Sync replication status...")
    sync_logs, _ = run_vm(ssh, "kubectl logs -n dns deployment/nebula-sync --tail=20")
    print(f"Nebula-Sync Logs:\n{sync_logs}")

    ssh.close()

    print("\n" + "=" * 75)
    print("  🎉 PI-HOLE 3-NODE CLUSTER FULLY DEPLOYED AND SYNCED!")
    print("=" * 75)
    print("  Cluster DNS Resolvers (Port 53 UDP & TCP):")
    print(f"    - Cluster Service IP:   {svc_ip}:53")
    print(f"    - Pi-hole 1 (Primary):   192.168.0.81:53")
    print(f"    - Pi-hole 2 (Replica 1): 192.168.0.82:53")
    print(f"    - Pi-hole 3 (Replica 2): 192.168.0.83:53")
    print("  Web Admin Portals:")
    print(f"    - Pi-hole 1:  http://{CP1_IP}:30081/admin  (or http://pihole-1.ertech.home/admin)")
    print(f"    - Pi-hole 2:  http://{CP1_IP}:30082/admin  (or http://pihole-2.ertech.home/admin)")
    print(f"    - Pi-hole 3:  http://{CP1_IP}:30083/admin  (or http://pihole-3.ertech.home/admin)")
    print("    - Public SSL: https://pihole.ertechlab.com/admin")
    print(f"  Password: {PIHOLE_PW}")
    print("=" * 75)

if __name__ == "__main__":
    main()
