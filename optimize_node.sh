#!/usr/bin/env bash
# ==============================================================================
# Proxmox VE Enterprise Cluster Node Optimization Script
# Target Nodes: pve-00 .. pve-04 (192.168.0.30 - 192.168.0.34)
# ==============================================================================
set -euo pipefail

NODE_NAME=$(hostname)
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "================================================================="
echo " Starting Proxmox VE Production Optimization on: ${NODE_NAME} (${IP_ADDR})"
echo "================================================================="

# 1. ROOT CHECK
if [[ $EUID -ne 0 ]]; then
   echo "[ERROR] This script must be run as root."
   exit 1
fi

# Detect Debian release codename (e.g. bookworm, bullseye)
DEBIAN_CODENAME=$(grep -oP 'VERSION_CODENAME=\K\w+' /etc/os-release || echo "bookworm")
echo "[+] Detected Debian codename: ${DEBIAN_CODENAME}"

# 2. REPOSITORY OPTIMIZATION (NO-SUBSCRIPTION REPO)
echo "[+] Configuring Proxmox VE no-subscription repositories..."

# Disable Enterprise repository
if [[ -f /etc/apt/sources.list.d/pve-enterprise.list ]]; then
    sed -i -E 's/^(deb\s+.*pve-enterprise)/# \1/' /etc/apt/sources.list.d/pve-enterprise.list
    echo "    - Disabled pve-enterprise.list"
fi

if [[ -f /etc/apt/sources.list.d/ceph.list ]]; then
    sed -i -E 's/^(deb\s+.*enterprise)/# \1/' /etc/apt/sources.list.d/ceph.list
    echo "    - Disabled ceph enterprise repository"
fi

# Ensure pve-no-subscription is enabled in /etc/apt/sources.list
if ! grep -q "pve-no-subscription" /etc/apt/sources.list; then
    echo "" >> /etc/apt/sources.list
    echo "# Proxmox VE No-Subscription Repository" >> /etc/apt/sources.list
    echo "deb http://download.proxmox.com/debian/pve ${DEBIAN_CODENAME} pve-no-subscription" >> /etc/apt/sources.list
    echo "    - Added pve-no-subscription repository"
fi

# 3. DISABLE THE "NO VALID SUBSCRIPTION" GUI NAG POPUP
echo "[+] Patching Proxmox Web GUI Subscription Nag Popup..."

PROXMOXLIB_JS="/usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js"
if [[ -f "${PROXMOXLIB_JS}" ]]; then
    # Backup original if not already backed up
    if [[ ! -f "${PROXMOXLIB_JS}.bak" ]]; then
        cp "${PROXMOXLIB_JS}" "${PROXMOXLIB_JS}.bak"
    fi

    # Patch the data.status check (both older and newer PVE 7/8 syntaxes)
    sed -i.bak -E 's/Ext.Msg.show\(\{\s+title:\s+gettext\(\x27No valid sub/void\(\{ \/\* & \*\//g' "${PROXMOXLIB_JS}"
    sed -i -E 's/res === null \|\| res === undefined \|\| \!res \|\| res\.data\.status\.toLowerCase\(\) \!== \x27active\x27/false/g' "${PROXMOXLIB_JS}"
    sed -i -E 's/if \(res\.data\.status\.toLowerCase\(\) \!== \x27active\x27\)/if \(false\)/g' "${PROXMOXLIB_JS}"
    echo "    - Patched ${PROXMOXLIB_JS}"

    # Create APT hook to re-patch automatically upon package upgrade
    cat <<'EOF' > /etc/apt/apt.conf.d/99-pve-disable-nag
DPkg::Post-Invoke {
    "which sed >/dev/null && test -f /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js && sed -i -E 's/Ext.Msg.show\(\{\s+title:\s+gettext\(\x27No valid sub/void\(\{ \/\* & \*\//g; s/res === null \|\| res === undefined \|\| \!res \|\| res\.data\.status\.toLowerCase\(\) \!== \x27active\x27/false/g; s/if \(res\.data\.status\.toLowerCase\(\) \!== \x27active\x27\)/if \(false\)/g' /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js || true";
};
EOF
    echo "    - Installed permanent APT post-invoke hook at /etc/apt/apt.conf.d/99-pve-disable-nag"
fi

# Restart pveproxy to apply GUI changes
systemctl restart pveproxy.service || true

# 4. CPU PERFORMANCE GOVERNOR TUNING
echo "[+] Setting CPU Governor to 'performance'..."
apt-get update -qq
apt-get install -y -qq cpufrequtils linux-cpupower || true

if command -v cpupower >/dev/null 2>&1; then
    cpupower frequency-set -g performance || true
fi

# Ensure performance governor persists across reboots via systemd
cat <<'EOF' > /etc/systemd/system/cpu-governor-performance.service
[Unit]
Description=Set CPU governor to performance for virtualization
After=sysinit.target local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do [ -f "$g" ] && echo performance > "$g" || true; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cpu-governor-performance.service

# 5. KERNEL SYSCTL VIRTUALIZATION OPTIMIZATIONS
echo "[+] Applying kernel sysctl virtualization profile..."
cat <<'EOF' > /etc/sysctl.d/99-pve-performance.conf
# Virtualization Swappiness (prevent aggressive disk swapping with RAM available)
vm.swappiness = 10

# Memory dirty page flush ratios (smoother disk I/O, prevents burst latency)
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5

# Maximum file handles
fs.file-max = 2097152

# Network socket backlog
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 16384

# Enable IPv4 packet forwarding (essential for LXC/K3s bridge routing)
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1

# Disable ICMP redirects for security
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
EOF

sysctl -p /etc/sysctl.d/99-pve-performance.conf >/dev/null

# 6. ZFS ARC TUNING (IF ZFS DETECTED)
if command -v zpool >/dev/null 2>&1 && zpool status >/dev/null 2>&1; then
    echo "[+] ZFS pool detected! Calculating ARC limit..."
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MEM_BYTES=$(( TOTAL_MEM_KB * 1024 ))
    
    # Cap ARC to 25% of total RAM to preserve memory for VMs
    ARC_MAX_BYTES=$(( TOTAL_MEM_BYTES / 4 ))
    ARC_MIN_BYTES=$(( ARC_MAX_BYTES / 2 ))
    
    cat <<EOF > /etc/modprobe.d/zfs.conf
# Cap ZFS ARC to prevent hypervisor OOM kills on guest VMs
options zfs zfs_arc_max=${ARC_MAX_BYTES}
options zfs zfs_arc_min=${ARC_MIN_BYTES}
EOF
    echo "    - Capped ZFS ARC Max to $(( ARC_MAX_BYTES / 1024 / 1024 / 1024 )) GB"
    if command -v update-initramfs >/dev/null 2>&1; then
        update-initramfs -u -k all >/dev/null 2>&1 &
    fi
fi

# 7. COROSYNC & CLUSTER QUORUM VERIFICATION
echo "[+] Verifying Corosync & Cluster Quorum..."
if command -v pvecm >/dev/null 2>&1; then
    pvecm status || echo "    - Warning: Node is not currently part of a clustered corosync state."
fi

echo "================================================================="
echo " Node ${NODE_NAME} Optimization Complete!"
echo " Web GUI: https://${IP_ADDR}:8006 (Nag disabled, no-sub active)"
echo "================================================================="
