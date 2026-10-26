#!/usr/bin/env bash
# Proxmox Ubuntu 24.04 Cloud-Init Template Creator
# Sourced from Notepad++ engineering notes

set -e

TEMPLATE_ID=9000
TEMPLATE_NAME="ubuntu-2404-cloudinit-template"
STORAGE_POOL="local-lvm"
IMAGE_URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
IMAGE_FILE="/var/lib/vz/template/iso/noble-server-cloudimg-amd64.img"

echo "=== Creating Ubuntu 24.04 LTS Cloud-Init Template (VMID: $TEMPLATE_ID) ==="

# Download official image if not already present
if [ ! -f "$IMAGE_FILE" ]; then
    echo "[*] Downloading Ubuntu 24.04 Noble cloud image..."
    wget -O "$IMAGE_FILE" "$IMAGE_URL"
fi

# Destroy existing template if present
qm destroy $TEMPLATE_ID 2>/dev/null || true

# 1. Create VM container shell
echo "[*] Initializing VM $TEMPLATE_ID..."
qm create $TEMPLATE_ID --name "$TEMPLATE_NAME" --memory 2048 --cores 2 --net0 virtio,bridge=vmbr0

# 2. Import disk to storage pool
echo "[*] Importing cloud disk..."
qm set $TEMPLATE_ID --scsihw virtio-scsi-pci --scsi0 $STORAGE_POOL:0,import-from=$IMAGE_FILE

# 3. Attach Cloud-Init Drive
echo "[*] Adding Cloud-Init drive..."
qm set $TEMPLATE_ID --ide2 $STORAGE_POOL:cloudinit

# 4. Set boot and serial display options
qm set $TEMPLATE_ID --boot c --bootdisk scsi0
qm set $TEMPLATE_ID --serial0 socket --vga serial0
qm set $TEMPLATE_ID --agent enabled=1

# 5. Convert to Proxmox Template
echo "[*] Converting VM to template..."
qm template $TEMPLATE_ID

echo "✓ Cloud-Init Template $TEMPLATE_ID ($TEMPLATE_NAME) successfully created!"
