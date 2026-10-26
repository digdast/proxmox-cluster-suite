#!/usr/bin/env bash
# ==============================================================================
# Proxmox VE Storage & Automated Backup Configuration
# Integrates cluster with Network Storage target: 192.168.0.3 (unRAID / NAS)
# ==============================================================================
set -euo pipefail

NFS_SERVER="${1:-192.168.0.3}"
NFS_EXPORT="${2:-/mnt/user/data/backups}"
STORAGE_ID="unraid-backups"

echo "================================================================="
echo " Configuring Shared NFS Storage & Backup Schedules"
echo " NFS Server: ${NFS_SERVER} | Export: ${NFS_EXPORT}"
echo "================================================================="

if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root on the Proxmox cluster."
   exit 1
fi

# 1. Test ping to NFS Server
if ! ping -c 1 -W 2 "${NFS_SERVER}" >/dev/null 2>&1; then
    echo "[!] Warning: NFS server ${NFS_SERVER} not responding to ICMP. Continuing..."
fi

# 2. Check if storage already registered in Proxmox
if pvesm status | grep -q "${STORAGE_ID}"; then
    echo "[+] Storage '${STORAGE_ID}' is already registered in cluster."
else
    echo "[+] Adding shared NFS storage '${STORAGE_ID}' to cluster..."
    # Attempt NFSv4 first, fallback to standard NFS
    pvesm add nfs "${STORAGE_ID}" \
        --server "${NFS_SERVER}" \
        --export "${NFS_EXPORT}" \
        --content backup,iso,vztmpl \
        --options vers=4.2,soft,timeo=30,retrans=2 || \
    pvesm add nfs "${STORAGE_ID}" \
        --server "${NFS_SERVER}" \
        --export "${NFS_EXPORT}" \
        --content backup,iso,vztmpl
    echo "[✓] Successfully registered '${STORAGE_ID}' across the cluster!"
fi

# 3. Configure Automated Daily Backup Schedule (vzdump)
echo "[+] Configuring daily automated cluster backups (3:00 AM)..."
CRON_JOB="# Proxmox Cluster Automated Backup to ${STORAGE_ID}
0 3 * * * root vzdump --all 1 --mode snapshot --compress zstd --storage ${STORAGE_ID} --mailnotification failure --quiet 1"

if ! grep -q "vzdump --all" /etc/cron.d/vzdump 2>/dev/null; then
    echo "${CRON_JOB}" > /etc/cron.d/cluster-vzdump
    echo "[✓] Backup cron scheduled at /etc/cron.d/cluster-vzdump"
else
    echo "[-] An existing vzdump schedule is already configured."
fi

echo "================================================================="
echo " NFS Storage & Backup Setup Complete!"
echo " Storage Status:"
pvesm status || true
echo "================================================================="
