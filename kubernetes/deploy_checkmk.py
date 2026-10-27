import paramiko
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
K8S_IP = "192.168.0.81"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(PVE_HOST, username=PVE_USER, password=PVE_PASS, timeout=15)

def run_k8s(cmd):
    escaped_cmd = cmd.replace("'", "'\\''")
    stdin, stdout, stderr = ssh.exec_command(f"ssh -o StrictHostKeyChecking=no root@{K8S_IP} '{escaped_cmd}'")
    out = stdout.read().decode('utf-8', errors='replace').strip()
    return out

CHECKMK_MANIFEST = """apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkmk
  namespace: monitoring
  labels:
    app: checkmk
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: checkmk
  template:
    metadata:
      labels:
        app: checkmk
    spec:
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: checkmk
        image: docker.io/checkmk/check-mk-community:2.5.0p16
        imagePullPolicy: IfNotPresent
        env:
        - name: CMK_SITE_ID
          value: "monitoring"
        securityContext:
          privileged: true
        ports:
        - containerPort: 5000
          name: http
        - containerPort: 8000
          name: agent-receiver
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 4000m
            memory: 4Gi
        volumeMounts:
        - name: sites
          mountPath: /omd/sites
        - name: sitetmp
          mountPath: /omd/sites/monitoring/tmp
        - name: localtime
          mountPath: /etc/localtime
          readOnly: true
      volumes:
      - name: sites
        hostPath:
          path: /var/lib/checkmk/sites
          type: DirectoryOrCreate
      - name: sitetmp
        emptyDir:
          medium: Memory
          sizeLimit: 1Gi
      - name: localtime
        hostPath:
          path: /etc/localtime
---
apiVersion: v1
kind: Service
metadata:
  name: checkmk
  namespace: monitoring
  labels:
    app: checkmk
spec:
  type: NodePort
  ports:
  - name: http
    port: 5000
    targetPort: 5000
    nodePort: 30500
  - name: agent-receiver
    port: 8000
    targetPort: 8000
    nodePort: 30800
  selector:
    app: checkmk
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: checkmk-ingress
  namespace: monitoring
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: checkmk-01.ertechlab.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: checkmk
            port:
              number: 5000
  - host: checkmk.ertechlab.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: checkmk
            port:
              number: 5000
  - host: checkmk-01.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: checkmk
            port:
              number: 5000
  - host: checkmk.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: checkmk
            port:
              number: 5000
"""

print("[*] Applying Checkmk Kubernetes Manifest...")
cmd = f"cat << 'EOF' > /tmp/checkmk-k8s.yaml\n{CHECKMK_MANIFEST}\nEOF\nkubectl apply -f /tmp/checkmk-k8s.yaml"
print(run_k8s(cmd))

time.sleep(3)
print("\n[*] Pods Status:")
print(run_k8s("kubectl get pods -n monitoring -o wide"))

ssh.close()
