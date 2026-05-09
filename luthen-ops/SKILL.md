---
name: luthen-ops
description: Use when performing software updates, modifying the cluster, adjusting firewall rules, or managing services (Khet, Jams, Infisical) on the luthen droplet at scromp.net.
---

# Luthen-Ops Playbook

## 1. Environment Details

*   **Host:** `luthen.scromp.net`
*   **Public IP:** `138.197.115.92`
*   **Private IP:** `10.132.152.72`
*   **Tailscale IP:** `100.89.158.108`
*   **Kubeconfig:** `/Users/bnaylor/k8s/luthen/kubeconfig` (Local)
*   **Manifests Root:** `/Users/bnaylor/k8s/luthen/` (Local)
    *   `infra/`: Shared DB, Redis, Infisical.
    *   `khet/`: Zipline deployment.
    *   `jams/`: Navidrome deployment.

## 2. Infrastructure Inventory

### 2.1 Kubernetes (MicroK8s)
*   **Namespace: `infra`**
    *   `postgres`: Shared PostgreSQL 16. Stores data for `infisical`, `zipline`, `navidrome`.
    *   `redis`: Shared Redis.
    *   `infisical`: Secrets management ([https://secrets.scromp.net](https://secrets.scromp.net)).
*   **Namespace: `khet`**
    *   `khet`: Zipline file sharing ([https://khet.scromp.net](https://khet.scromp.net)).
*   **Namespace: `music`**
    *   `jams`: Navidrome music streamer ([https://jams.scromp.net](https://jams.scromp.net)).
*   **Namespace: `default`**
    *   `legacy-apache`: Service/Ingress for host-level Apache ([https://luthen.scromp.net](https://luthen.scromp.net)).
    *   `blackhole`: Catch-all for unrecognized hostnames (returns 418).

### 2.2 Storage (The "Living Overlay")
*   **LUN:** 50GB mounted at `/mnt/space`.
*   **Layout:**
    *   `/mnt/space/postgres_data`: Persistent DB files.
    *   `/mnt/space/navidrome_data`: Navidrome internal state.
    *   `/mnt/space/khet_uploads`: Native Zipline uploads.
*   **User Web Data:**
    *   Stored in `/home/<user>/html`.
    *   Mounted into Navidrome via `hostPath` at `/music/<user>`.

## 3. Access Control Playbook

### 3.1 Firewall (nftables)
*   Config: `/etc/nftables.conf` (Host).
*   Whitelist Strategy:
    *   **Public:** 80/443 (Web), 41641 (Tailscale).
    *   **SSH Whitelist:** Only specific IPs (chumdrop, davidc, ashish, gemini-cli).
    *   **Tailscale:** Full access.

### 3.2 Identities
*   **UIDs/GIDs:** Replicated from `umbra` to preserve permissions.
    *   `bnaylor`: 1000
    *   `ashish`: 6674
    *   `davidc`: 1005

## 4. Operational Workflows

### 4.1 Applying Changes
1.  Edit manifest in `~/k8s/luthen/<app>/`.
2.  Run: `KUBECONFIG=~/k8s/luthen/kubeconfig kubectl apply -f ...`

### 4.2 Database Access
*   `kubectl exec -n infra deployment/postgres -- psql -U postgres`

### 4.3 Adding an SSH IP
1.  Edit `/etc/nftables.conf`.
2.  Run: `nft -f /etc/nftables.conf`

## 5. Maintenance Mandates
*   **Always** update this skill when adding new services or changing infrastructure IPs.
*   **Always** commit manifest changes to the local k8s directory.
*   **Verify** before declaring success (use `curl -I` and `kubectl get pods`).

## 6. Critical Decisions Record
*   **Shared Postgres:** Use a single instance for all apps to conserve RAM (4GB droplet limit).
*   **Living Overlay:** Mounting home dirs directly into K8s instead of moving data into PVs.
*   **Blackhole Ingress:** Catch-all ingress to return 418 and reduce scanner reconnaissance.
