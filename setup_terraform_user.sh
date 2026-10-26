#!/usr/bin/env bash
# Proxmox VE Terraform & Ansible Automation User Setup
# Sourced from Notepad++ engineering notes

set -e

USER_NAME="automation"
REALM="pve"
FULL_USER="${USER_NAME}@${REALM}"
ROLE="Administrator"

echo "=== Creating Proxmox Automation API User ($FULL_USER) ==="

# 1. Create a terraform/ansible user
pveum user add $FULL_USER --comment "Automated Terraform & Ansible CI/CD Service Account"

# 2. Assign role for infrastructure automation
pveum aclmod / -user $FULL_USER -role $ROLE

# 3. Generate API Token
TOKEN_NAME="terraform"
echo "[*] Generating API Token for $FULL_USER..."
pveum user token add $FULL_USER $TOKEN_NAME --privsep 0

echo "✓ Automation user and API token generated successfully!"
