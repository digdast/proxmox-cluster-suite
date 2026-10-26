#!/usr/bin/env bash
# ==============================================================================
# Proxmox VE K3s Kubernetes on LXC Provisioning & Optimization
# Configures unprivileged nested LXC containers for HA K3s
# ==============================================================================
set -euo pipefail

CT_ID="${1:-200}"
CT_NAME="${2:-k3s-master-01}"
CT_IP="${3:-192.168.0.40/24}"
GATEWAY="${4:-192.168.0.1}"
BRIDGE="${5:-vmbr0}"
STORAGE="${6:-local-lvm}"

echo "================================================================="
echo " Provisioning K3s Container #${CT_ID} (${CT_NAME}) on $(hostname)"
echo " IP: ${CT_IP} | Gateway: ${GATEWAY}"
echo "================================================================="

if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root on Proxmox VE."
   exit 1
fi

# Ensure Ubuntu 22.04 or Debian 12 template is available
TEMPLATE="local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst"
if ! pveam list "${STORAGE%%-*}" | grep -q "debian-12"; then
    echo "[+] Downloading Debian 12 standard template..."
    pveam update
    pveam download local debian-12-standard_12.7-1_amd64.tar.zst || true
fi

# Create LXC container with Kubernetes nesting and keyctl features
echo "[+] Creating LXC container ${CT_ID}..."
pct create "${CT_ID}" "${TEMPLATE}" \
    --hostname "${CT_NAME}" \
    --cores 2 \
    --memory 2048 \
    --swap 512 \
    --features nesting=1,keyctl=1 \
    --unprivileged 1 \
    --ostype debian \
    --net0 "name=eth0,bridge=${BRIDGE},ip=${CT_IP},gw=${GATEWAY}" \
    --storage "${STORAGE}" \
    --rootfs "${STORAGE}:16" \
    --onboot 1

# Configure LXC cgroups v2 and apparmor delegation for Kubernetes/K3s
CONF_FILE="/etc/pve/lxc/${CT_ID}.conf"
echo "[+] Tuning LXC configuration at ${CONF_FILE} for K3s..."

cat <<'EOF' >> "${CONF_FILE}"

# Kubernetes & K3s Container Optimizations
lxc.apparmor.profile: unconfined
lxc.cgroup2.devices.allow: a
lxc.cap.drop:
lxc.mount.auto: proc:rw sys:rw
EOF

# Start Container
echo "[+] Starting container ${CT_ID}..."
pct start "${CT_ID}"
sleep 3

# Install K3s inside the container
echo "[+] Installing K3s inside container ${CT_ID}..."
pct exec "${CT_ID}" -- bash -c '
    apt-get update -qq && apt-get install -y -qq curl ca-certificates iptables
    curl -sfL https://get.k3s.io | sh -s - --disable traefik --write-kubeconfig-mode 644
'

echo "================================================================="
echo " K3s LXC Container ${CT_ID} Ready!"
echo " Check node status: pct exec ${CT_ID} -- kubectl get nodes"
echo "================================================================="
