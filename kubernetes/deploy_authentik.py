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

AUTHENTIK_MANIFEST = """apiVersion: v1
kind: Namespace
metadata:
  name: authentik
---
apiVersion: v1
kind: Secret
metadata:
  name: authentik-secret
  namespace: authentik
type: Opaque
stringData:
  AUTHENTIK_SECRET_KEY: "BEEkcehzf2bZ4770XrzCfdYByQPHVEpXKlg0VeaiExYC0yrLGmFbrQTd8P6eEXpv"
  AUTHENTIK_POSTGRESQL__PASSWORD: "uj2tzzWUeOpfn"
  AUTHENTIK_POSTGRESQL__USER: "authentik"
  AUTHENTIK_POSTGRESQL__NAME: "authentik"
  AUTHENTIK_POSTGRESQL__HOST: "authentik-postgresql"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: authentik-config
  namespace: authentik
data:
  AUTHENTIK_REDIS__HOST: "authentik-redis"
  AUTHENTIK_ERROR_REPORTING__ENABLED: "false"
  AUTHENTIK_DISABLE_STARTUP_ANALYTICS: "true"
  AUTHENTIK_DISABLE_UPDATE_CHECK: "false"
  AUTHENTIK_LISTEN__HTTP: "0.0.0.0:9000"
  AUTHENTIK_LISTEN__HTTPS: "0.0.0.0:9443"
  AUTHENTIK_LISTEN__LDAP: "0.0.0.0:3389"
  AUTHENTIK_LISTEN__LDAPS: "0.0.0.0:6636"
  AUTHENTIK_EVENTS__CONTEXT_PROCESSORS__GEOIP: "/data/geoip/GeoLite2-City.mmdb"
  AUTHENTIK_EVENTS__CONTEXT_PROCESSORS__ASN: "/data/geoip/GeoLite2-ASN.mmdb"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authentik-postgresql
  namespace: authentik
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: authentik-postgresql
  template:
    metadata:
      labels:
        app: authentik-postgresql
    spec:
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: postgresql
        image: postgres:17-alpine
        imagePullPolicy: IfNotPresent
        env:
        - name: POSTGRES_DB
          value: "authentik"
        - name: POSTGRES_USER
          value: "authentik"
        - name: POSTGRES_PASSWORD
          value: "uj2tzzWUeOpfn"
        ports:
        - containerPort: 5432
          name: postgresql
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        volumeMounts:
        - name: pgdata
          mountPath: /var/lib/postgresql/data
        - name: pgdump
          mountPath: /dump
      volumes:
      - name: pgdata
        hostPath:
          path: /var/lib/authentik/postgresql
          type: DirectoryOrCreate
      - name: pgdump
        hostPath:
          path: /var/lib/authentik/dump
          type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: authentik-postgresql
  namespace: authentik
spec:
  ports:
  - port: 5432
    targetPort: 5432
  selector:
    app: authentik-postgresql
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authentik-redis
  namespace: authentik
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: authentik-redis
  template:
    metadata:
      labels:
        app: authentik-redis
    spec:
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: redis
        image: redis:alpine
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 6379
          name: redis
        resources:
          requests:
            cpu: 50m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
        volumeMounts:
        - name: redisdata
          mountPath: /data
      volumes:
      - name: redisdata
        hostPath:
          path: /var/lib/authentik/redis
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: authentik-redis
  namespace: authentik
spec:
  ports:
  - port: 6379
    targetPort: 6379
  selector:
    app: authentik-redis
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authentik-server
  namespace: authentik
  labels:
    app: authentik-server
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: authentik-server
  template:
    metadata:
      labels:
        app: authentik-server
    spec:
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: server
        image: ghcr.io/goauthentik/server:2026.8.5
        imagePullPolicy: IfNotPresent
        args: ["server"]
        envFrom:
        - secretRef:
            name: authentik-secret
        - configMapRef:
            name: authentik-config
        ports:
        - containerPort: 9000
          name: http
        - containerPort: 9443
          name: https
        - containerPort: 3389
          name: ldap
        - containerPort: 6636
          name: ldaps
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
        volumeMounts:
        - name: media
          mountPath: /media
        - name: templates
          mountPath: /templates
        - name: certs
          mountPath: /certs
        - name: blueprints
          mountPath: /blueprints
      volumes:
      - name: media
        hostPath:
          path: /var/lib/authentik/data/media
          type: DirectoryOrCreate
      - name: templates
        hostPath:
          path: /var/lib/authentik/data/templates
          type: DirectoryOrCreate
      - name: certs
        hostPath:
          path: /var/lib/authentik/data/certs
          type: DirectoryOrCreate
      - name: blueprints
        hostPath:
          path: /var/lib/authentik/data/blueprints
          type: DirectoryOrCreate
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authentik-worker
  namespace: authentik
  labels:
    app: authentik-worker
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: authentik-worker
  template:
    metadata:
      labels:
        app: authentik-worker
    spec:
      nodeSelector:
        kubernetes.io/hostname: k8s-cp-01
      containers:
      - name: worker
        image: ghcr.io/goauthentik/server:2026.8.5
        imagePullPolicy: IfNotPresent
        args: ["worker"]
        envFrom:
        - secretRef:
            name: authentik-secret
        - configMapRef:
            name: authentik-config
        resources:
          requests:
            cpu: 250m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
        volumeMounts:
        - name: media
          mountPath: /media
        - name: templates
          mountPath: /templates
        - name: certs
          mountPath: /certs
        - name: blueprints
          mountPath: /blueprints
      volumes:
      - name: media
        hostPath:
          path: /var/lib/authentik/data/media
          type: DirectoryOrCreate
      - name: templates
        hostPath:
          path: /var/lib/authentik/data/templates
          type: DirectoryOrCreate
      - name: certs
        hostPath:
          path: /var/lib/authentik/data/certs
          type: DirectoryOrCreate
      - name: blueprints
        hostPath:
          path: /var/lib/authentik/data/blueprints
          type: DirectoryOrCreate
---
apiVersion: v1
kind: Service
metadata:
  name: authentik
  namespace: authentik
  labels:
    app: authentik
spec:
  type: NodePort
  ports:
  - name: http
    port: 9000
    targetPort: 9000
    nodePort: 30090
  - name: https
    port: 9443
    targetPort: 9443
    nodePort: 30443
  - name: ldap
    port: 3389
    targetPort: 3389
    nodePort: 30389
  - name: ldaps
    port: 6636
    targetPort: 6636
    nodePort: 30636
  selector:
    app: authentik-server
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: authentik-ingress
  namespace: authentik
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: auth.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: authentik
            port:
              number: 9000
  - host: authentik.ertech.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: authentik
            port:
              number: 9000
  - host: auth.ertechlab.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: authentik
            port:
              number: 9000
"""

print("[*] Applying Authentik Kubernetes Manifest...")
cmd = f"cat << 'EOF' > /tmp/authentik-k8s.yaml\n{AUTHENTIK_MANIFEST}\nEOF\nkubectl apply -f /tmp/authentik-k8s.yaml"
print(run_k8s(cmd))

time.sleep(3)
print("\n[*] Pods Status:")
print(run_k8s("kubectl get pods -n authentik -o wide"))

ssh.close()
