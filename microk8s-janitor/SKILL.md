---
name: microk8s-janitor
description: Automates rolling upgrades and maintenance for HA MicroK8s clusters on Ubuntu via SSH. Supports node discovery, channel selection, pre-flight checks, and stateful recovery.
---

# MicroK8s Janitor

This skill manages the lifecycle of a MicroK8s cluster, specifically focusing on safe, rolling upgrades of nodes to ensure high availability is maintained throughout the process.

## Prerequisites

- SSH access to at least one node in the cluster (the "seed" node).
- Passwordless `sudo` or SSH key-based authentication for the user.
- The `microk8s` snap must be installed on the target nodes.

## Core Workflows

### 1. Cluster Discovery & Environment Setup

Starting from a single seed node provided by the user, the janitor discovers the full cluster state.

1. **Seed Connection:** Connect to the seed node and run `microk8s kubectl get nodes -o json`.
2. **Node Mapping:** Parse the output to identify all nodes, their roles, and current statuses.
3. **Connectivity Check:** Verify SSH and `sudo` access to every node in the cluster.
4. **Channel Discovery:** Run `snap info microk8s` on the seed node to list available tracking channels (e.g., `1.28/stable`, `latest/edge`).

### 2. Pre-flight Checks (The "Dry Run")

Before any disruptive action, the janitor ensures the cluster is healthy:

- All nodes must be in the `Ready` status.
- Check for any "critical" pods (e.g., `Longhorn`, `Calico`, `CoreDNS`) that are currently in a non-running state.
- Verify that `dqlite` (the HA backend) has a healthy quorum.

### 3. Interactive Planning

Present the plan to the user:
- Current version vs. Target channel.
- The order of nodes to be upgraded.
- Ask for confirmation before proceeding.

### 4. Rolling Upgrade Loop (Sequential Execution)

For each node in the sequence:

1. **Cordon:** `microk8s kubectl cordon <node-name>`
2. **Drain:** `microk8s kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force`
3. **Upgrade:** `sudo snap refresh microk8s --channel=<channel>`
4. **Wait for Ready:** Poll `microk8s status --wait-ready` (max 5 minutes).
5. **Health Check:** Verify local pods are starting and node status is `Ready`.
6. **Uncordon:** `microk8s kubectl uncordon <node-name>`

### 5. Resume & Recovery

If a step fails:
- **Abort:** Stop immediately. Do not move to the next node.
- **Log:** Capture and display the error from the node.
- **State Check:** On re-invocation, the janitor detects if any nodes are still cordoned and offers to "Resume" the upgrade from the failed node.

## Helm & StatefulSet Management

### The "Immutable Wall"
When upgrading stateful applications (PostgreSQL, MongoDB, Redis) via Helm, changing certain fields (like `storageClass` or `volumeClaimTemplates`) will cause a `Forbidden` error because `StatefulSet` templates are immutable.

### The Stateful Upgrade Workflow
To resolve immutable field errors:
1. **Identify**: Confirm the error is due to immutable fields in a \`StatefulSet\`.
2. **Preservation Decision**:
   - If data MUST be kept: Ensure the PVC has a `Retain` or `Delete` policy that allows it to persist (or orphan) after the StatefulSet is deleted.
   - If a clean slate is intended: Prepare to delete the PVC as well.
3. **Destructive Action**: Delete the specific StatefulSet directly:
   \`\`\`bash
   kubectl delete statefulset <name> -n <namespace>
   \`\`\`
4. **Re-apply**: Re-run the `helm upgrade` or `helm install` command. Helm will now successfully recreate the StatefulSet with the new spec.

## Best Practices

- **Quorum First:** Never upgrade more than one node at a time in a 3-node HA cluster to avoid losing quorum.
- **Drain Timeout:** If a drain hangs, report the specific pod causing the delay to the user.
- **Snap Rollback:** If `snap refresh` fails, attempts `snap revert microk8s` if appropriate.

## Cluster Access (bnaylor's cluster)

- **Local kubectl:** `kubectl` works directly from the Mac via `~/.kube/config` — no SSH needed for cluster operations.
- **API server:** `https://10.3.2.4:16443` (microk8s-cluster)
- **Docker Hub user:** `bnaylor` — already authenticated locally.

## Deploying Services to This Cluster

### General workflow for Python services (e.g. running-proxy)

**Always cross-build for `linux/amd64`** — even pure Python services use pip packages with native binaries (uvicorn, pydantic-core, cryptography, greenlet, etc.) that are architecture-specific. Building natively on an ARM64 Mac produces an image that crashes with `exec format error` on the x86_64 cluster nodes.

```bash
docker buildx build --platform linux/amd64 -t bnaylor/<service>:latest --push .
kubectl rollout restart deployment/<service> -n <namespace>
kubectl rollout status deployment/<service> -n <namespace>
```

- `--push` in the buildx command pushes directly, skipping a separate `docker push` step.
- If `docker push` gets a 504 on a plain push, retry once — layers are already cached.

### running-proxy service

- **Namespace:** `running-proxy`
- **Image:** `bnaylor/running-proxy:latest`
- **External IP:** `10.3.2.132` (LoadBalancer, port 80 → container 8000)
- **Deployment YAMLs:** `~/k8s/running-proxy/yamls/`
- **Secrets:** `running-proxy-secrets` (spreadsheet-id), `google-service-account-json` (service-account.json)
- **Storage:** NFS PVC `running-proxy-data` mounted at `/app/data` (SQLite lives there); strategy is `Recreate` to avoid concurrent writers

### LiteLLM (noc cluster)

- **Namespace:** `litellm`
- **Image:** `ghcr.io/berriai/litellm:main`
- **External IP:** `10.3.2.135` (LoadBalancer, port 8000)
- **Config:** `litellm-config` ConfigMap in `litellm` namespace.

#### Software Version Discovery (LiteLLM)

Determining the version of LiteLLM in the cluster is non-trivial because the CLI and package attributes are inconsistent.

**Effective Methods:**
1. **Check pyproject.toml (Most Reliable for source version):**
   ```bash
   kubectl exec -n litellm <pod-name> -- cat /app/pyproject.toml | grep version
   ```
2. **Check pip list (Reliable for installed package):**
   ```bash
   kubectl exec -n litellm <pod-name> -- pip list | grep litellm
   ```
3. **Check Git Commit (For development builds):**
   ```bash
   kubectl exec -n litellm <pod-name> -- cat /app/.git/refs/heads/main
   ```
4. **Image Digest (Most definitive for release date):**
   ```bash
   kubectl get pod <pod-name> -n litellm -o jsonpath="{.status.containerStatuses[0].imageID}"
   ```

**Known Failures (Don't use these):**
- ❌ `litellm --version` (Throws an error or shows help)
- ❌ `python3 -c "import litellm; print(litellm.__version__)"` (AttributeError: module 'litellm' has no attribute '__version__')
- ❌ `/version` HTTP endpoint (Returns 404 in many configurations)

