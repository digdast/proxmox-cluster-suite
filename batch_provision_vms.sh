#!/usr/bin/env bash
# Batch VM Provisioning across Proxmox Cluster Nodes (pve-00 to pve-04)
# Sourced from Notepad++ engineering notes

set -e

TEMPLATE_ID=9000
START_ID=100
NODES=("pve-00" "pve-01" "pve-02" "pve-03" "pve-04")

echo "=== Batch Provisioning Proxmox Cluster VMs ==="

for i in "${!NODES[@]}"; do
    VM_ID=$((START_ID + i))
    NODE="${NODES[$i]}"
    VM_NAME="ubuntu-srv-${NODE}"
    
    echo "[*] Cloning template $TEMPLATE_ID to VM $VM_ID ($VM_NAME) on node $NODE..."
    qm clone $TEMPLATE_ID $VM_ID --name "$VM_NAME" --full 1 --target "$NODE"
    
    # Configure custom resources if needed
    qm set $VM_ID --cores 2 --memory 4096
    
    echo "  ✓ VM $VM_ID ($VM_NAME) cloned successfully on $NODE."
done

echo "=== All VMs successfully provisioned! ==="
