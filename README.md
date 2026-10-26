# ⚡ Proxmox VE 5-Node Enterprise Cluster Suite

Comprehensive optimization, high-availability tuning, automated backup, and monitoring suite tailored for the **5-Node Proxmox VE Cluster** (`pve-00` to `pve-04` at `192.168.0.30 - 192.168.0.34`) and network storage (`192.168.0.3` unRAID / NAS).

---

## 🖥️ Cluster Topology

| Node Name | IP Address | PVE Web GUI | Role |
| :--- | :--- | :--- | :--- |
| **`pve-00`** | `192.168.0.30` | [https://192.168.0.30:8006](https://192.168.0.30:8006) | Master / Primary Node |
| **`pve-01`** | `192.168.0.31` | [https://192.168.0.31:8006](https://192.168.0.31:8006) | Node 1 / Compute Worker |
| **`pve-02`** | `192.168.0.32` | [https://192.168.0.32:8006](https://192.168.0.32:8006) | Node 2 / Compute Worker |
| **`pve-03`** | `192.168.0.33` | [https://192.168.0.33:8006](https://192.168.0.33:8006) | Node 3 / Compute Worker |
| **`pve-04`** | `192.168.0.34` | [https://192.168.0.34:8006](https://192.168.0.34:8006) | Node 4 / Compute Worker |
| **`unRAID`** | `192.168.0.3` | [//192.168.0.3/data](file:///192.168.0.3/data) | Shared NFS Backups & Media Pool |

---

## 🚀 Key Modules Included

### 1. Production Performance Tuning (`optimize_node.sh`)
- **No-Subscription Repositories**: Disables invalid enterprise repos and enables `pve-no-subscription` so `apt update` works seamlessly.
- **Nag Popup Removal**: Patches `proxmoxlib.js` to eliminate the *"No Valid Subscription"* popup. Includes a permanent APT post-invoke hook in `/etc/apt/apt.conf.d/` so the patch survives updates.
- **CPU Governor**: Sets CPU governor to `performance` across all cores via persistent systemd service, preventing hypervisor micro-stutters.
- **Kernel Sysctl**:
  - `vm.swappiness = 10`: Keeps VM memory cached in RAM instead of aggressive paging.
  - `vm.dirty_ratio = 10` & `vm.dirty_background_ratio = 5`: Smoother write flush.
  - `net.ipv4.ip_forward = 1`: Enabled for LXC and K3s bridge routing.
- **ZFS ARC Cap**: Automatically caps ZFS ARC memory to 25% of node RAM to prevent hypervisor OOM kills on guest VMs.

### 2. Shared Storage & Automated Backups (`setup_nfs_backups.sh`)
- Auto-registers NFS share from `192.168.0.3` (`/mnt/user/data/backups`) across the cluster.
- Configures automated daily `vzdump` snapshots with zstd compression at 3:00 AM.

### 3. K3s Kubernetes on LXC (`k3s_lxc_setup.sh`)
- Pre-provisions unprivileged nested LXC containers with `features: nesting=1,keyctl=1`.
- Configures cgroups v2 and AppArmor delegation for smooth containerized workloads.

### 4. Interactive 1-Click Orchestrator (`orchestrator.py` & `run_suite.bat`)
- Multi-threaded Python dispatcher using Paramiko.
- Prompts for your root password or SSH key once, and applies tuning concurrently across all 5 nodes.

### 5. Cluster Web Dashboard (`web_dashboard.py` on port 7880)
- Real-time status cards for all 5 nodes and storage target.
- Live latency pinging and 1-click web console launcher.

---

## 🛠️ Quick Start

### Option A: 1-Click Interactive Dispatcher
Double click:
`C:\scripts\proxmox_orchestrator.bat`

### Option B: Web Dashboard
Double click:
`C:\scripts\proxmox_dashboard.bat` (opens `http://localhost:7880`)

### Option C: Manual Run on Any Node
You can also copy and run `optimize_node.sh` directly on any node:
```bash
scp C:\scripts\proxmox_cluster_suite\optimize_node.sh root@192.168.0.30:/tmp/
ssh root@192.168.0.30 "chmod +x /tmp/optimize_node.sh && /tmp/optimize_node.sh"
```

## Kubernetes HA Cluster & Workloads
Automated provisioning, storage, and orchestration scripts for the 6-node K3s cluster:
- `kubernetes/deploy_k8s_cluster.py`: Deploy 2 Control Planes & 4 Workers with embedded etcd HA.
- `kubernetes/deploy_portainer_k8s.py`: Deploy Portainer CE connected to in-cluster Kubernetes API.
- `kubernetes/configure_nfs_all_nodes.py`: Mount Unraid NFS storage (`/mnt/user/data`) across all nodes.
- `kubernetes/add_ssh_keys_to_cluster.py`: Inject SSH keys into root and plexadmin on all nodes.
- `kubernetes/deploy_media_stack.py`: Deploy Sonarr, Radarr, and Prowlarr with persistent NFS storage.
- `kubernetes/deploy_plex.py`: Deploy Plex Media Server with persistent library mounts.
- `kubernetes/deploy_full_pihole_cluster.py`: Deploy 3-node Pi-hole v6 + Unbound + DoH cluster with Nebula-Sync.
- `kubernetes/expand_all_cluster_disks.py`: Live online disk expansion (+40GB) across all 6 nodes.
- `kubernetes/expand_all_cluster_ram.py`: RAM expansion (+2GB to 6GB) with hotplug support.
- `kubernetes/sync_local_dns_from_pihole01.py`: Copy and sync all 49 local DNS records from pihole-01.
